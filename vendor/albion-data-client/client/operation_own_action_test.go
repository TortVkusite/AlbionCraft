package client

import (
	"encoding/json"
	"github.com/ao-data/albiondata-client/lib"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestOwnActionWaitsForSuccessAndNeverTreatsBrowsingAsCreation(t *testing.T) {
	router := newRouter()
	l := newListener(router)
	l.onRequest(byte(opAuctionCreateRequest), map[byte]interface{}{253: uint16(opAuctionCreateRequest), 0: int64(9007199254740993)})
	select {
	case <-router.newOperation:
		t.Fatal("request alone changed own orders")
	default:
	}
	l.onResponse(byte(opAuctionCreateRequest), -1, "", map[byte]interface{}{253: uint16(opAuctionCreateRequest)})
	select {
	case <-router.newOperation:
		t.Fatal("failed creation changed own orders")
	default:
	}
	raw := `{"Id":9007199254740993,"ItemTypeId":"T3_2H_BOW","Amount":10,"UnitPriceSilver":5150000,"QualityLevel":1}`
	l.onRequest(byte(opAuctionCreateRequest), map[byte]interface{}{253: uint16(opAuctionCreateRequest)})
	l.onResponse(byte(opAuctionCreateRequest), 0, "", map[byte]interface{}{253: uint16(opAuctionCreateRequest), 0: []string{raw}})
	op := <-router.newOperation
	action, ok := op.(*operationOwnActionResponse)
	if !ok {
		t.Fatalf("creation routed publicly: %T", op)
	}
	rows := action.Payload["Orders"].([]map[string]interface{})
	if len(rows) != 1 || rows[0]["Id"].(json.Number).String() != "9007199254740993" {
		t.Fatal("creation precision or identity lost")
	}
}

func TestCancellationCorrelatesOnlyItsConfirmedRequest(t *testing.T) {
	l := newListener(newRouter())
	l.rememberOwnAction(map[byte]interface{}{253: uint16(opAuctionAbortOffer), 0: int64(9007199254740993)})
	op := l.confirmedOwnAction(opAuctionAbortOffer, 0, map[byte]interface{}{253: uint16(opAuctionAbortOffer)}).(*operationOwnActionResponse)
	ids := op.Payload["OrderIds"].([]string)
	if len(ids) != 1 || ids[0] != "9007199254740993" {
		t.Fatal(ids)
	}
	l.rememberOwnAction(map[byte]interface{}{253: uint16(opAuctionAbortOffer), 0: int64(1), 1: int64(2)})
	op = l.confirmedOwnAction(opAuctionAbortOffer, 0, map[byte]interface{}{253: uint16(opAuctionAbortOffer)}).(*operationOwnActionResponse)
	if op.Payload["OrderIds"] != nil {
		t.Fatal("ambiguous request cancelled an arbitrary order")
	}
}

func TestNewMailLayoutAndLocalReadForBuySummary(t *testing.T) {
	oldURL := OwnOrdersURL
	oldMail := MailInfos
	defer func() { OwnOrdersURL = oldURL; MailInfos = oldMail }()
	var received map[string]interface{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&received)
		w.WriteHeader(200)
	}))
	defer server.Close()
	OwnOrdersURL = server.URL
	ticks := int64(621355968000000000) + time.Now().Unix()*10000000
	op, err := decodeResponse(map[byte]interface{}{253: uint16(opGetMailInfos), 3: []int{50}, 7: []string{"0007"}, 11: []string{"MARKETPLACE_BUYORDER_FINISHED_SUMMARY"}, 12: []int64{ticks}})
	if err != nil {
		t.Fatal(err)
	}
	state := &albionState{LocationId: "0007", CharacterId: lib.CharacterID("owner"), CharacterName: "Player"}
	op.Process(state)
	operationReadMail{ID: 50, Body: "10|T3_2H_BOW|51500000|5150000"}.Process(state)
	if received["Action"] != "mail" || received["Confirmed"] != true {
		t.Fatal(received)
	}
	mail := received["Mail"].(map[string]interface{})
	if mail["Received"] == "" || mail["Type"] != "MARKETPLACE_BUYORDER_FINISHED_SUMMARY" {
		t.Fatal(mail)
	}
	operationReadMail{ID: 50, Body: "short"}.Process(state) // Must not panic on malformed body.
}
