package khan_linter

// In order to download golangci-lint and all its dependencies source code,
// We need to create this empty main go module, to import golangci-lint module.
// The command `go mod tidy` will add any dependencies needed for golangci-lint,
// the command `go mod vendor` will create vendor directory, and download all
// dependencies into it which include golangci-lint source code too.
import (
	_ "github.com/golangci/golangci-lint/cmd/golangci-lint"
)
