package client

import (
	"bytes"
	"encoding/json"
	"github.com/ao-data/albiondata-client/log"
	"net/http"
	"net/url"
	"strings"
	"time"
)

var OwnOrdersURL string

type operationOwnOrdersResponse struct {
	MarketOrders []string `mapstructure:"0"`
	Side         string
	Finished     bool
}

// Own orders are sent exclusively to the explicitly configured loopback target.
// Never route these through public, private, or websocket uploaders.
func (op operationOwnOrdersResponse) Process(state *albionState) {
	orders := make([]map[string]interface{}, 0, len(op.MarketOrders))
	for _, raw := range op.MarketOrders {
		var entry map[string]interface{}
		decoder := json.NewDecoder(strings.NewReader(raw))
		decoder.UseNumber()
		if decoder.Decode(&entry) == nil {
			orders = append(orders, entry)
		}
	}
	sendOwnPayload(state, map[string]interface{}{"Side": op.Side, "Orders": orders, "Complete": false, "Finished": op.Finished})
}

func sendOwnPayload(state *albionState, payload map[string]interface{}) {
	target, err := url.Parse(OwnOrdersURL)
	if err != nil || target.Scheme != "http" || target.Hostname() != "127.0.0.1" || target.User != nil {
		return
	}
	if state.CharacterId == "" || !state.IsValidLocation() {
		return
	}
	payload["CharacterId"] = state.CharacterId
	payload["CharacterName"] = state.CharacterName
	payload["LocationId"] = state.LocationId
	if payload["Observed"] == nil {
		payload["Observed"] = time.Now().UTC().Format(time.RFC3339Nano)
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return
	}
	req, err := http.NewRequest("POST", OwnOrdersURL, bytes.NewReader(data))
	if err != nil {
		return
	}
	req.Header.Set("Content-Type", "application/json")
	response, err := (&http.Client{Timeout: 5 * time.Second}).Do(req)
	if err != nil {
		log.Warnf("Own orders: local receiver unavailable: %v", err)
		return
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		log.Warnf("Own orders: local receiver status %d", response.StatusCode)
		return
	}
	log.Info("Own orders: sent private observation locally")
}
