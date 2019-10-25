# Prefer generic style array types in flow (flow-array-type-style)

In flow, array types can be written as `T[]` or `Array<T>`.  When the type is
nullable, the former can be consfusing, e.g.

```
?T[] = ?Array<T>
(?T)[] = Array<?T>
```

This rule prefers the `Array<T>` for array types to avoid the confusion.

## Rule Details

The following are considered warnings:

```js
type foo = number[]
type foo = ?number[]
type foo = (?number)[]
```

The following are not considered warnings:

```js
type foo = Array<number>
type foo = ?Array<number>
type foo = Array<?number>
```
