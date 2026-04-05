package device

import "os"

func ResolveDeviceID(explicit string) string {
	if explicit != "" {
		return explicit
	}
	h, err := os.Hostname()
	if err != nil || h == "" {
		return "unknown-device"
	}
	return h
}

func ResolveHostname() string {
	h, err := os.Hostname()
	if err != nil || h == "" {
		return "unknown-host"
	}
	return h
}
