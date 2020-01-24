module khan_linter

go 1.12

require github.com/golangci/golangci-lint v1.21.0

require gopkg.in/yaml.v2 v2.2.7 // Lock the version to the same as golangci-lint

// https://github.com/golangci/golangci-lint/pull/937
// https://github.com/Khan/golangci-lint/tree/custom-autofix
replace github.com/golangci/golangci-lint => github.com/Khan/golangci-lint v1.21.1-0.20200124164953-d5b1882bad50

// https://github.com/golang/tools/pull/156
// https://github.com/golang/tools/pull/160
replace golang.org/x/tools => github.com/golangci/tools v0.0.0-20190915081525-6aa350649b1c
