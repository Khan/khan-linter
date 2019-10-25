const rule = require("../lib/rules/react-no-subscriptions-before-mount");
const RuleTester = require("eslint").RuleTester;

const parserOptions = {
    parser: "babel-eslint",
};

const ruleTester = new RuleTester(parserOptions);
const message = rule.__message;
const errors = [message];

const validBecauseNoSubs = `
class MyComponent extends Component {
    constructor(props) {
        super(props);

        this.state = {
            yadda: 5,
        };
    }

    componentWillMount() {
        console.log('Will mount!');
    }
}`;
const validBecauseSubAfterMount = `
class MyComponent extends Component {
    componentDidMount() {
        window.addEventListener('scroll', () => {})
    }
}`;

const invalidBecausePromiseInConstructor = `
class MyComponent extends Component {
    constructor(props) {
        super(props);

        load().then(components => {
            this.state = {
                yadda: 5,
            };
        });
    }
}`;

const invalidBecausePromiseInCWM = `
class MyComponent extends Component {
    constructor(props) {
        super(props);

        this.state = {
            yadda: 5,
        };
    }

    componentWillMount() {
        const {load} = this.props;

        load().then(components => {
            this.setState({components});
        });
    }
}`;

const invalidBecauseEventListener = `
class MyComponent extends Component {
    componentWillMount() {
        window.addEventListener('scroll', function() {});
    }
}`;

const invalidBecauseSetTimeoutAsGlobal = `
class MyComponent extends Component {
    componentWillMount() {
        setTimeout(function() {}, 1000);
    }
}`;

const invalidBecauseSetTimeoutAsProperty = `
class MyComponent extends Component {
    componentWillMount() {
        window.setTimeout(function() {}, 1000);
    }
}`;

const invalidBecauseSubWithinBlock = `
class MyComponent extends Component {
    componentWillMount() {
        if (this.whatever = 10) {
            window.addEventListener('scroll', function() {});
        }
    }
}`;

const invalidWithNestedProperty = `
class MyComponent extends Component {
    componentWillMount() {
        document.body.addEventListener('scroll', function() {});
    }
}`;

const invalidWithinPromise = `
class MyComponent extends Component {
    componentWillMount() {
        this.promise = new Promise((resolve, reject) => {
            setTimeout(function() {}, 1000)
        })
    }
}`;

// TODO (josh): This example currently passes, but it should fail.
// Once the rule is less naive, add this example to the invalid tests.
// eslint-disable-next-line
const TODOInvalid = `
class MyComponent extends Component {
    componentWillMount() {
        this.subscribeToInfo();
    }

    subscribeToInfo() {
        api.fetch().then(() => {

        });
    }
}`;

ruleTester.run("bind-react-methods", rule, {
    valid: [validBecauseNoSubs, validBecauseSubAfterMount],

    invalid: [
        invalidBecausePromiseInConstructor,
        invalidBecausePromiseInCWM,
        invalidBecauseEventListener,
        invalidBecauseSetTimeoutAsGlobal,
        invalidBecauseSetTimeoutAsProperty,
        invalidBecauseSubWithinBlock,
        invalidWithNestedProperty,
        invalidWithinPromise,
        // TODOInvalid,
    ].map(code => ({code, errors})),
});
