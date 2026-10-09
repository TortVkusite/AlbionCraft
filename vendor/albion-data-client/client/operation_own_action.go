package client

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"
)

type ownActionRequest struct {
	Params map[byte]interface{}
	At     time.Time
}
type operationOwnActionResponse struct{ Payload map[string]interface{} }

func (op *operationOwnActionResponse) Process(state *albionState) { sendOwnPayload(state, op.Payload) }

func ownAction(code OperationType) (string, string) {
	switch code {
	case opAuctionCreateOffer:
		return "created", "sell"
	case opAuctionCreateRequest:
		return "created", "buy"
	case opAuctionModifyAuction:
		return "modified", "mixed"
	case opAuctionAbortOffer:
		return "cancelled", "sell"
	case opAuctionAbortRequest:
		return "cancelled", "buy"
	case opAuctionAbortAuction:
		return "cancelled", "mixed"
	}
	return "", ""
}

// Only complete canonical order objects are accepted; positional fields of
// unknown protocol revisions are kept locally, never guessed into a purchase.
func canonicalOwnOrders(value interface{}) []map[string]interface{} {
	var result []map[string]interface{}
	switch v := value.(type) {
	case string:
		if !strings.HasPrefix(strings.TrimSpace(v), "{") {
			return result
		}
		var obj map[string]interface{}
		d := json.NewDecoder(strings.NewReader(v))
		d.UseNumber()
		if d.Decode(&obj) == nil {
			return canonicalOwnOrders(obj)
		}
	case map[string]interface{}:
		if v["Id"] != nil && v["ItemTypeId"] != nil && v["Amount"] != nil && v["UnitPriceSilver"] != nil && v["QualityLevel"] != nil {
			result = append(result, v)
		}
	case map[byte]interface{}:
		for k, x := range v {
			if k != 253 && k != 255 {
				result = append(result, canonicalOwnOrders(x)...)
			}
		}
	case []string:
		for _, x := range v {
			result = append(result, canonicalOwnOrders(x)...)
		}
	case []interface{}:
		for _, x := range v {
			result = append(result, canonicalOwnOrders(x)...)
		}
	}
	return result
}

func positiveOrderID(value interface{}) (string, bool) {
	switch v := value.(type) {
	case string:
		if _, err := strconv.ParseUint(v, 10, 64); err == nil && v != "0" {
			return v, true
		}
	case int64:
		if v > 0 {
			return strconv.FormatInt(v, 10), true
		}
	case uint64:
		if v > 0 {
			return strconv.FormatUint(v, 10), true
		}
	case int:
		if v > 0 {
			return strconv.Itoa(v), true
		}
	case int32:
		if v > 0 {
			return strconv.FormatInt(int64(v), 10), true
		}
	case json.Number:
		if _, err := strconv.ParseUint(string(v), 10, 64); err == nil && v != "0" {
			return string(v), true
		}
	}
	return "", false
}

func (l *listener) rememberOwnAction(params map[byte]interface{}) {
	code, ok := resolveOperationCode(params)
	if !ok {
		return
	}
	if action, _ := ownAction(OperationType(code)); action == "" {
		return
	}
	if l.ownPending == nil {
		l.ownPending = map[OperationType][]ownActionRequest{}
	}
	copied := map[byte]interface{}{}
	for k, v := range params {
		copied[k] = v
	}
	// Bound stale requests, including missing responses, to avoid unbounded state.
	queue := l.ownPending[OperationType(code)]
	fresh := []ownActionRequest{}
	for _, q := range queue {
		if time.Since(q.At) < 15*time.Second {
			fresh = append(fresh, q)
		}
	}
	if len(fresh) >= 8 {
		fresh = fresh[1:]
	}
	l.ownPending[OperationType(code)] = append(fresh, ownActionRequest{copied, time.Now()})
}

func (l *listener) confirmedOwnAction(code OperationType, rc int16, response map[byte]interface{}) operation {
	action, side := ownAction(code)
	if action == "" {
		return nil
	}
	queue := l.ownPending[code]
	delete(l.ownPending, code)
	var request map[byte]interface{}
	if len(queue) == 1 && time.Since(queue[0].At) < 15*time.Second {
		request = queue[0].Params
	}
	if len(queue) > 1 {
		// Multiple concurrent operations need the same transaction marker.
		for n, q := range queue {
			if response[255] != nil && fmt.Sprint(response[255]) == fmt.Sprint(q.Params[255]) && time.Since(q.At) < 15*time.Second {
				request = q.Params
				l.ownPending[code] = append(queue[:n], queue[n+1:]...)
				break
			}
		}
	}
	if rc != 0 {
		return nil
	}
	orders := canonicalOwnOrders(response)
	payload := map[string]interface{}{"Action": action, "Side": side, "Confirmed": true, "Observed": time.Now().UTC().Format(time.RFC3339Nano), "Operation": code.String(), "Request": request, "Response": response, "Orders": orders}
	if action == "cancelled" && request != nil {
		ids := []string{}
		for key, value := range request {
			if key != 253 && key != 255 {
				if id, ok := positiveOrderID(value); ok {
					ids = append(ids, id)
				}
			}
		}
		if len(ids) == 1 {
			payload["OrderIds"] = ids
		}
	}
	return &operationOwnActionResponse{payload}
}
