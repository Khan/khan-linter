# Disallow subscriptions before React components have mounted (react-no-subscriptions-before-mount)

React components should avoid doing any sort of async work (data fetching,
event listeners, timeouts, etc) before the component has mounted.

There are two main reasons for this:

- We want to avoid these subscriptions on the server
- Starting in React 16, `componentWillMount` may be called multiple times
per mount.

## Rule Details

The two methods called before mount are `constructor` and `componentWillMount`.
This rule warns for signs of async work (eg. `addEventListener`, `setTimeout`,
`.then`)

The following are considered warnings:

```js
class Foo extends Component {
    constructor() {
        super();

        fetchData().then(...)
    }
}

class Foo extends Component {
    componentWillMount() {
        window.addEventListener(...)
    }
}
```

The following are not considered warnings:

```js
class Foo extends Component {
    componentDidMount() {
        fetchData().then(...)
    }
}
```
