# Require exact object types for State (flow-exact-state)

Using exact object types for State can help types when there are optional
state properties.

This rule supports autofixing.  Please note, this may result in new flow
errors.

## Rule Details

The following are considered warnings:

```js
type Props = {| x: number |};
type State = { x: number };
class Foo extends React.Component<Props, State> {}
```

```js
type FooProps = {| x: number |};
type FooState = { x: number };
class Foo extends React.Component<FooProps, FooState> {}
```

The following are not considered warnings:

```js
type Props = { x: number };
type State = {| x: number |};
class Foo extends React.Component<Props, State> {}
```

```js
type FooProps = { x: number };
type BarState = { x: number };
type FooState = {| x: number |};
class Foo extends React.Component<FooProps, FooState> {
```
