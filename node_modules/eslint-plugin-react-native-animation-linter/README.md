
ESLint plugin for detecting React Native Animation bugs
=======================================================

Lint rules to ensure safe management of React Native animations.

# Installation

Install [ESLint](https://www.github.com/eslint/eslint).

```sh
$ npm install eslint
```

Install eslint-plugin-react-native-animation-linter

```sh
$ npm install eslint-plugin-react-native-animation-linter
```

# Configuration

Add `plugins` section and specify react-native-animation-linter as a plugin.

```json
{
  "plugins": [
    "react-native-animation-linter"
  ]
}
```

Finally, enable the rules that you would like to use.
(There is currently only one rule, but we may add more!)

```json
{
  "rules": {
    "react-native-animation-linter/must-tear-down-animations": 2,
  }
}
```

# List of supported rules

* [must-tear-down-animations](docs/rules/must-tear-down-animations.md): Detect animated state variables that aren't torn down properly.


