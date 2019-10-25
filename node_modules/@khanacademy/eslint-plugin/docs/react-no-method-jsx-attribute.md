# Prevent passing methods as props to other components (react-no-method-jsx-attribute)

Passing methods as props without pre-binding is a common mistake in React programming.  
Components created using `createReactClass` avoid this issue because `createReactClass`
pre-binds all non-lifecycle methods.

This eslint rule warns against passing methods as props to other components and suggests
using class properties instead.  This ensure that `this` is correct when the component 
receiving the props calls it.

## Rule Details

The following are considered warnings:

```js
class Foo extends React.Component {
    handleClick() {}
    
    render() {
        return <div onClick={this.handleClick}>
    }
}
```

```js
class Foo extends React.Component {
    handleBaz() {}
    
    render() {
        return <Bar onBaz={this.handleBaz}>
    }
}
```

The following are not considered warnings:

```js
class Foo extends React.Component {
    handleClick = () => {}
    
    render() {
        return <div onClick={this.handleClick}>
    }
}
```

```js
class Foo extends React.Component {
    handleClick() {}
    
    render() {
        return <div onClick={() => this.handleClick()}>
    }
}
```

```js
class Foo extends React.Component {
    constructor(props) {
        super(props);
        this.handleClick = () => {};
    }
    
    render() {
        return <div onClick={this.handleClick}>
    }
}
```

```js
class Foo extends React.Component {
    get bar() {
        return this._bar;
    }

    render() {
        return <div id={this.bar} />
    }
}
```
