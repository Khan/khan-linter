const path = require("path");

const {rules} = require("../lib/index.js");
const RuleTester = require("eslint").RuleTester;

const parserOptions = {
    parser: "babel-eslint",
};

const ruleTester = new RuleTester(parserOptions);
const rule = rules["react-no-method-jsx-attribute"];

ruleTester.run("react-no-method-jsx-attribute", rule, {
    valid: [
        // method arrow function in constructor
        {
            code: `
class Foo {
    constructor() {
        this.handleClick = () => {};
    }

    render() {
        return <div onClick={this.handleClick} />
    }
}`,
            options: [],
        },
        // method arrow function class property
        {
            code: `
class Foo {
    handleClick = () => {}

    render() {
        return <div onClick={this.handleClick} />
    }
}`,
            options: [],
        },
        // different classes using the same event handler
        {
            code: `
class Foo {
    handleClick = () => {}

    render() {
        return <div onClick={this.handleClick} />
    }
}

class Bar {
    handleClick() {}

    render() {
        return <div onClick={() => this.handleClick()} />
    }
}`,
            options: [],
        },
        // getter method - called in Foo's scope so it's fine
        {
            code: `
class Foo {
    get bar() {
        return this._bar;
    }

    render() {
        return <div id={this.bar} />
    }
}`,
            options: [],
        },
    ],
    invalid: [
        // regular method, not okay
        {
            code: `
class Foo {
    handleClick() {}

    render() {
        return <div onClick={this.handleClick} />
    }
}`,
            options: [],
            errors: [
                "Methods cannot be passed as props, use a class property instead.",
            ],
        },
        // two regular methods, both not okay, two errors
        {
            code: `
class Foo {
    handleClick() {}

    render() {
        return <div onClick={this.handleClick} />
    }
}

class Bar {
    handleClick() {}

    render() {
        return <div onClick={this.handleClick} />
    }
}`,
            options: [],
            errors: [
                "Methods cannot be passed as props, use a class property instead.",
                "Methods cannot be passed as props, use a class property instead.",
            ],
        },
    ],
});
