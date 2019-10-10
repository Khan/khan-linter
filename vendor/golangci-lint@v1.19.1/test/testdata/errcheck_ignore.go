//args: -Eerrcheck
//config_path: testdata/errcheck/ignore_config.yml
package testdata

import (
	"fmt"
	"io/ioutil"
	"os"
)

func TestErrcheckIgnoreOs() {
	_, _ = os.Open("f.txt")
}

func TestErrcheckNoIgnoreFmt(s string) int {
	n, _ := fmt.Println(s) // ERROR "Error return value of `fmt.Println` is not checked"
	return n
}

func TestErrcheckIgnoreIoutil() []byte {
	ret, _ := ioutil.ReadFile("f.txt")
	return ret
}

func TestErrcheckNoIgnoreIoutil() []byte {
	ret, _ := ioutil.ReadAll(nil) // ERROR "Error return value of `ioutil.ReadAll` is not checked"
	return ret
}
