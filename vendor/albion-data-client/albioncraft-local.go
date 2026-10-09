// Local-only capture entry point. No game requests or self-updates.
package main

import (
	"flag"
	"github.com/ao-data/albiondata-client/client"
	"github.com/ao-data/albiondata-client/log"
	"net/url"
	"strings"
)

func main() {
	flag.StringVar(&client.OwnOrdersURL, "own-orders", "", "Loopback AlbionCraft own-order receiver")
	client.ConfigGlobal.SetupFlags()
	// A manually started copy must also never fall back to external upload targets.
	targets := []string{}
	for _, raw := range strings.Split(client.ConfigGlobal.PublicIngestBaseUrls, ",") {
		target, err := url.Parse(raw)
		if err == nil && target.Scheme == "http" && target.Hostname() == "127.0.0.1" && target.User == nil {
			targets = append(targets, raw)
		}
	}
	client.ConfigGlobal.PublicIngestBaseUrls = strings.Join(targets, ",")
	client.ConfigGlobal.PrivateIngestBaseUrls = ""
	client.ConfigGlobal.EnableWebsockets = false
	if client.ConfigGlobal.PrintVersion {
		log.Info("AlbionCraft local capture 2 (AODP source; confirmed order events)")
		return
	}
	if err := client.NewClient("AlbionCraft-local-2").Run(); err != nil {
		log.Error(err)
	}
}
