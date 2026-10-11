package client

import (
	"encoding/json"
	"github.com/ao-data/albiondata-client/lib"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestOwnOrdersDecodedWithSideAndSentOnlyLocally(t *testing.T) {
	old := OwnOrdersURL
	defer func() { OwnOrdersURL = old }()
	var received map[string]interface{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Albion-Server") != "2" {
			t.Errorf("own orders lost server identity: %q", r.Header.Get("X-Albion-Server"))
		}
		d := json.NewDecoder(r.Body)
		d.UseNumber()
		d.Decode(&received)
		w.WriteHeader(200)
	}))
	defer server.Close()
	OwnOrdersURL = server.URL
	state := &albionState{AODataServerID: 2, LocationId: "0007", CharacterId: lib.CharacterID("owner"), CharacterName: "Player"}
	for code, side := range map[OperationType]string{opAuctionGetMyOpenOffers: "sell", opAuctionGetMyOpenRequests: "buy", opAuctionGetMyOpenAuctions: "mixed"} {
		op, err := decodeResponse(map[byte]interface{}{253: uint16(code), 0: []string{`{"Id":9007199254740993,"ItemTypeId":"T3_2H_BOW","Amount":10,"UnitPriceSilver":5150000,"QualityLevel":1,"EnchantmentLevel":0}`}})
		if err != nil {
			t.Fatal(err)
		}
		own, ok := op.(*operationOwnOrdersResponse)
		if !ok || own.Side != side {
			t.Fatalf("own response side lost: %#v", op)
		}
		own.Process(state)
		if received["Side"] != side || received["CharacterId"] != "owner" {
			t.Fatalf("bad payload: %v", received)
		}
		entry := received["Orders"].([]interface{})[0].(map[string]interface{})
		if entry["Id"].(json.Number).String() != "9007199254740993" {
			t.Fatal("order ID precision lost")
		}
	}
	received = nil
	OwnOrdersURL = "https://example.invalid/ownorders.ingest"
	operationOwnOrdersResponse{Side: "buy"}.Process(state)
	if received != nil {
		t.Fatal("own data sent to a nonlocal target")
	}
}

func TestListenerPreservesOwnOperationIdentity(t *testing.T) {
	router := newRouter()
	listener := newListener(router)
	for _, code := range []OperationType{opAuctionGetMyOpenOffers, opAuctionGetMyOpenRequests, opAuctionGetMyOpenAuctions} {
		listener.onResponse(byte(code), 0, "", map[byte]interface{}{253: uint16(code), 0: []string{}})
		select {
		case op := <-router.newOperation:
			if _, ok := op.(*operationOwnOrdersResponse); !ok {
				t.Fatalf("own orders routed as public: %T", op)
			}
		default:
			t.Fatal("own response not dispatched")
		}
	}
	listener.onResponse(byte(opAuctionGetMyOpenOffers), -1, "", map[byte]interface{}{253: uint16(opAuctionGetMyOpenOffers), 0: []string{}})
	select {
	case <-router.newOperation:
		t.Fatal("failed request changed own snapshot")
	default:
	}
}
