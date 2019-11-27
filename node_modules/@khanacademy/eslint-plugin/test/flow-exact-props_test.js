const {rules} = require("../lib/index.js");
const RuleTester = require("eslint").RuleTester;

const parserOptions = {
    parser: "babel-eslint",
};

const ruleTester = new RuleTester(parserOptions);
const rule = rules["flow-exact-props"];

const message = rule.__message;
const errors = [message];

ruleTester.run("flow-exact-props", rule, {
    valid: [
        {
            code: `
        type Props = {| x: number |};
        class Foo extends React.Component<Props> {}`,
        },
        {
            code: `
        type BarProps = { x: number };
        type FooProps = {| x: number |};
        class Foo extends React.Component<FooProps> {}`,
        },
        {
            code: `
        type Props = {| x: number |};
        const Foo = (props: Props) => {}`,
        },
    ],
    invalid: [
        {
            code: `
        type Props = { x: number };
        class Foo extends React.Component<Props> {}`,
            errors: ['"Props" type should be exact'],
            output: `
        type Props = {| x: number |};
        class Foo extends React.Component<Props> {}`,
        },
        {
            code: `
        type FooProps = { x: number };
        class Foo extends React.Component<FooProps> {}`,
            errors: ['"FooProps" type should be exact'],
            output: `
        type FooProps = {| x: number |};
        class Foo extends React.Component<FooProps> {}`,
        },
        {
            code: `
        type FooProps = { x: number };
        class Foo extends React.Component<FooProps> {}
        type BarProps = { x: number };
        class Bar extends React.Component<BarProps> {}`,
            errors: [
                '"FooProps" type should be exact',
                '"BarProps" type should be exact',
            ],
            output: `
        type FooProps = {| x: number |};
        class Foo extends React.Component<FooProps> {}
        type BarProps = {| x: number |};
        class Bar extends React.Component<BarProps> {}`,
        },
        {
            code: `
type Props = { x: number };
const Foo = (props: Props) => {}`,
            errors: ['"Props" type should be exact'],
            output: `
type Props = {| x: number |};
const Foo = (props: Props) => {}`,
        },
    ],
});
