# Disallow one-tuples in flow (flow-no-one-tuple)

A common mistake people make, when starting to use Flow, is to assume that
arrays of a type can be expressed by wrapping the type in brackets (eg.
`[number]`).

This expression _actually_ refers to a tuple, which is an array that holds a
finite number of items, each with their type specified. The correct expression
would be `Array<number>`.

To help avoid this mistake, we warn against the uncommon pattern of a
single-value tuple.

## Rule Details

The following are considered warnings:

```js
type foo = [number]
```

The following are not considered warnings:

```js
type foo = Array<number>
type foo = [number, number]
```

If you actually need a one-tuple, the rule can be disabled, e.g.

```js
type foo = [number]  // eslint-disable-line flow-no-one-tuple
```
