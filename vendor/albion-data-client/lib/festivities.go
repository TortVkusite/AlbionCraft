package lib

// FestivitiesUpload contains the current scheduled Albion events.
type FestivitiesUpload struct {
	Events []*Festivity `json:"Events"`
}

// Festivity contains one scheduled Albion event.
type Festivity struct {
	Kind       uint8  `json:"Kind"`
	Category   string `json:"Category"`
	UniqueName string `json:"UniqueName"`
	StartTime  int64  `json:"StartTime"`
	EndTime    int64  `json:"EndTime"`
}
