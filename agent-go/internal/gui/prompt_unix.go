//go:build !windows

package gui

import (
    "bufio"
    "fmt"
    "os"
    "strings"
)

func promptFolderSelection(currentPaths []string, writeEnv bool) string {
    if len(currentPaths) > 1 || (len(currentPaths) == 1 && !isDefaultPath(currentPaths[0])) {
        return ""
    }

    fmt.Println("No scan path configured.")
    fmt.Print("Enter the folder path(s) to scan (comma-separated) [default: $HOME]: ")

    scanner := bufio.NewScanner(os.Stdin)
    scanner.Scan()
    input := strings.TrimSpace(scanner.Text())

    if input == "" {
        home, err := os.UserHomeDir()
        if err != nil || home == "" {
            return ""
        }
        input = home
    }

    if writeEnv && input != "" {
        writePathToEnv(input)
    }

    return input
}