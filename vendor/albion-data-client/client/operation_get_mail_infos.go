package client

import (
	"fmt"
	"time"

	"github.com/ao-data/albiondata-client/log"
)

var MailInfos MailInfosLookup

type MailInfosLookup []MailInfo

func (mi MailInfosLookup) getMailInfo(id int) *MailInfo {
	for i := range mi {
		if mi[i].ID == id {
			return &mi[i]
		}
	}
	return nil
}

type MailInfo struct {
	Received   string
	ID         int    `json:"MailId"`     // mapstructure:"3"
	LocationID string `json:"LocationId"` // mapstructure:"6"
	OrderType  string `json:"OrderType"`  // mapstructure:"10"
	Expires    int64  `json:"Expires"`    // mapstructure:"11"
}

func (m *MailInfo) StringArray() []string {
	return []string{
		fmt.Sprintf("%d", m.ID),
		m.LocationID,
		m.OrderType,
		m.StringExpires(),
	}
}

func (m *MailInfo) StringExpires() string {
	return time.Unix(m.Expires, 0).Format(time.RFC3339)
}

type operationGetMailInfosResponse struct {
	Received   []int64  `mapstructure:"12"`
	MailIDs    []int    `mapstructure:"3"`  // mapstructure:"3"
	Locations  []string `mapstructure:"6"`  // mapstructure:"6"
	OrderTypes []string `mapstructure:"10"` // mapstructure:"10"
	Expires    []int64  `mapstructure:"11"` // mapstructure:"11"
}

func (op operationGetMailInfosResponse) Process(state *albionState) {
	log.Debugf("Got response to GetMailInfos operation")

	for i := range op.MailIDs {
		if i >= len(op.Locations) || i >= len(op.OrderTypes) {
			continue
		}
		mail := &MailInfo{}
		mail.ID = op.MailIDs[i]
		mail.LocationID = op.Locations[i]
		mail.OrderType = op.OrderTypes[i]
		if i < len(op.Expires) {
			mail.Expires = op.Expires[i]
		}
		if i < len(op.Received) {
			ticks := op.Received[i]
			if ticks >= 621355968000000000 {
				mail.Received = time.Unix((ticks-621355968000000000)/10000000, ((ticks-621355968000000000)%10000000)*100).UTC().Format(time.RFC3339Nano)
			}
		}
		if previous := MailInfos.getMailInfo(mail.ID); previous != nil {
			*previous = *mail
		} else {
			MailInfos = append(MailInfos, *mail)
		}
	}

	if len(MailInfos) < 1 {
		log.Info("Mail Infos Response - no mails\n\n")
		return
	}

	log.Infof("Mail Infos - Cached %d mail infos", len(MailInfos))
}
