package checkers

import (
	"fmt"
	"go/ast"
	"go/token"
	"go/types"

	"golang.org/x/tools/go/analysis"

	"github.com/Antonboom/testifylint/internal/analysisutil"
)

// Empty detects situations like
//
//	assert.Len(t, arr, 0)
//	assert.Equal(t, 0, len(arr))
//	assert.EqualValues(t, 0, len(arr))
//	assert.Exactly(t, 0, len(arr))
//	assert.LessOrEqual(t, len(arr), 0)
//	assert.GreaterOrEqual(t, 0, len(arr))
//	assert.Less(t, len(arr), 0)
//	assert.Greater(t, 0, len(arr))
//	assert.Less(t, len(arr), 1)
//	assert.Greater(t, 1, len(arr))
//
//	assert.NotEqual(t, 0, len(arr))
//	assert.NotEqualValues(t, 0, len(arr))
//	assert.Less(t, 0, len(arr))
//	assert.Greater(t, len(arr), 0)
//
// and requires
//
//	assert.Empty(t, arr)
//	assert.NotEmpty(t, arr)
type Empty struct{}

// NewEmpty constructs Empty checker.
func NewEmpty() Empty      { return Empty{} }
func (Empty) Name() string { return "empty" }

func (checker Empty) Check(pass *analysis.Pass, call *CallMeta) *analysis.Diagnostic {
	if d := checker.checkEmpty(pass, call); d != nil {
		return d
	}
	return checker.checkNotEmpty(pass, call)
}

func (checker Empty) checkEmpty(pass *analysis.Pass, call *CallMeta) *analysis.Diagnostic { //nolint:gocognit
	newUseEmptyDiagnostic := func(replaceStart, replaceEnd token.Pos, replaceWith ast.Expr) *analysis.Diagnostic {
		const proposed = "Empty"
		return newUseFunctionDiagnostic(checker.Name(), call, proposed,
			newSuggestedFuncReplacement(call, proposed, analysis.TextEdit{
				Pos:     replaceStart,
				End:     replaceEnd,
				NewText: analysisutil.NodeBytes(pass.Fset, replaceWith),
			}),
		)
	}

	if len(call.Args) < 2 {
		return nil
	}
	a, b := call.Args[0], call.Args[1]

	switch call.Fn.NameFTrimmed {
	case "Len":
		if isZero(b) {
			return newUseEmptyDiagnostic(a.Pos(), b.End(), a)
		}

	case "Equal", "EqualValues", "Exactly":
		arg1, ok1 := isLenCallAndZero(pass, a, b)
		arg2, ok2 := isLenCallAndZero(pass, b, a)

		if lenArg, ok := anyVal([]bool{ok1, ok2}, arg1, arg2); ok {
			return newUseEmptyDiagnostic(a.Pos(), b.End(), lenArg)
		}

	case "LessOrEqual":
		if lenArg, ok := isBuiltinLenCall(pass, a); ok && isZero(b) {
			return newUseEmptyDiagnostic(a.Pos(), b.End(), lenArg)
		}

	case "GreaterOrEqual":
		if lenArg, ok := isBuiltinLenCall(pass, b); ok && isZero(a) {
			return newUseEmptyDiagnostic(a.Pos(), b.End(), lenArg)
		}

	case "Less":
		if lenArg, ok := isBuiltinLenCall(pass, a); ok && (isOne(b) || isZero(b)) {
			return newUseEmptyDiagnostic(a.Pos(), b.End(), lenArg)
		}

	case "Greater":
		if lenArg, ok := isBuiltinLenCall(pass, b); ok && (isOne(a) || isZero(a)) {
			return newUseEmptyDiagnostic(a.Pos(), b.End(), lenArg)
		}
	}
	return nil
}

func (checker Empty) checkNotEmpty(pass *analysis.Pass, call *CallMeta) *analysis.Diagnostic { //nolint:gocognit
	newUseNotEmptyDiagnostic := func(replaceStart, replaceEnd token.Pos, replaceWith ast.Expr) *analysis.Diagnostic {
		const proposed = "NotEmpty"
		return newUseFunctionDiagnostic(checker.Name(), call, proposed,
			newSuggestedFuncReplacement(call, proposed, analysis.TextEdit{
				Pos:     replaceStart,
				End:     replaceEnd,
				NewText: analysisutil.NodeBytes(pass.Fset, replaceWith),
			}),
		)
	}

	if len(call.Args) < 2 {
		return nil
	}
	a, b := call.Args[0], call.Args[1]

	switch call.Fn.NameFTrimmed {
	case "NotEqual", "NotEqualValues":
		arg1, ok1 := isLenCallAndZero(pass, a, b)
		arg2, ok2 := isLenCallAndZero(pass, b, a)

		if lenArg, ok := anyVal([]bool{ok1, ok2}, arg1, arg2); ok {
			return newUseNotEmptyDiagnostic(a.Pos(), b.End(), lenArg)
		}

	case "Less":
		if lenArg, ok := isBuiltinLenCall(pass, b); ok && isZero(a) {
			return newUseNotEmptyDiagnostic(a.Pos(), b.End(), lenArg)
		}

	case "Greater":
		if lenArg, ok := isBuiltinLenCall(pass, a); ok && isZero(b) {
			return newUseNotEmptyDiagnostic(a.Pos(), b.End(), lenArg)
		}
	}
	return nil
}

var lenObj = types.Universe.Lookup("len")

func isLenCallAndZero(pass *analysis.Pass, a, b ast.Expr) (ast.Expr, bool) {
	lenArg, ok := isBuiltinLenCall(pass, a)
	return lenArg, ok && isZero(b)
}

func isBuiltinLenCall(pass *analysis.Pass, e ast.Expr) (ast.Expr, bool) {
	ce, ok := e.(*ast.CallExpr)
	if !ok {
		return nil, false
	}

	if analysisutil.IsObj(pass.TypesInfo, ce.Fun, lenObj) && len(ce.Args) == 1 {
		return ce.Args[0], true
	}
	return nil, false
}

func isZero(e ast.Expr) bool {
	return isIntNumber(e, 0)
}

func isOne(e ast.Expr) bool {
	return isIntNumber(e, 1)
}

func isIntNumber(e ast.Expr, v int) bool {
	bl, ok := e.(*ast.BasicLit)
	return ok && bl.Kind == token.INT && bl.Value == fmt.Sprintf("%d", v)
}
