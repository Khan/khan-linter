module khan_linter

go 1.12

require github.com/golangci/golangci-lint v1.21.0

// https://github.com/golangci/golangci-lint/pull/841
replace github.com/golangci/golangci-lint => github.com/dbraley/golangci-lint v1.21.1-0.20200110145939-8a72db8a2a50

// https://github.com/golang/tools/pull/156
// https://github.com/golang/tools/pull/160
replace golang.org/x/tools => github.com/golangci/tools v0.0.0-20190915081525-6aa350649b1c
