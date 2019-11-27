# Require exact object types for Props (flow-exact-props)

Using exact object types for Props can help identify extra props and in
the case of optional props, typos.

This rule supports autofixing.  Please note, this may result in new flow
errors.

## Rule Details

The following are considered warnings:

```js
type Props = { x: number };
class Foo extends React.Component<Props> {}
```

```js
type FooProps = { x: number };
class Foo extends React.Component<FooProps> {}
```

```js
type Props = { x: number };
const Foo = (props: Props) => {}
```

The following are not considered warnings:

```js
type Props = {| x: number |};
class Foo extends React.Component<Props> {}
```

```js
type BarProps = { x: number };
type FooProps = {| x: number |};
class Foo extends React.Component<FooProps> {}
```

```js
type Props = {| x: number |};
const Foo = (props: Props) => {}
```
