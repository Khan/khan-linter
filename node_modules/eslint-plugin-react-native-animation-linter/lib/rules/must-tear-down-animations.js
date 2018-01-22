/**
 * Attempts to enforce that animations are torn down when component unmounts.
 */
const { astHelpers } = require("../util/animations");

const create = context => {
  // If we imported Animated from somewhere other than "react-native", all
  // bets are off
  let unexpectedImport = false;

  // Stores all animated values that have been set (keyed by component)
  // When an animation is torn down, it is removed.
  const activeAnimations = {};

  /**
   * Report teardown violations (animations that are set but not
   * torn down in componentWillUnmount)
   */
  function reportMissingTeardowns() {
    // If we've determined that Animated isn't actually from react-native,
    // we ignore all detected "violations".
    if (unexpectedImport) {
      return;
    }
    // Get list of all animated nodes that remain active (not torn down)
    const componentAnimations = Object.values(activeAnimations);
    // Iterate through all nodes failing the lint rule
    // and use context.report to surface error to user.
    componentAnimations.forEach(activeNodes => {
      Object.values(activeNodes).forEach(node => {
        context.report({
          node: node,
          message: `Must tear down animations when component unmounts`
        });
      });
    });
  }

  /**
   * Check state initialization. If state is set to an animated value
   * directly we record the animation.
   */
  function checkAnimatedStateInitialization(node, componentAnimations) {
    const stateProperty = _getStateInitialization(node);
    if (stateProperty) {
      // If initializing state with an animation directly, record the animation
      const expression = node.value.callee;
      const isAnimation = astHelpers.isAnimationDeclaration(expression);
      if (isAnimation) {
        _updateAnimationRecord(node, stateProperty);
      } else if (node.value.type === "Identifier") {
        const allVariablesInScope = context.getScope().variables;
        // If we're setting state to a variable, check the current scope
        // to determine if that variable has been set to an animated value.
        allVariablesInScope.forEach(variable => {
          if (variable.name !== node.value.name) {
            return;
          }
          const isAnimatedState = _checkIsStateVariableAnimated(variable);
          if (isAnimatedState) {
            _updateAnimationRecord(node, stateProperty);
          }
        });
      }
    }
  }

  /**
   * Check setState calls. If state is set to an animated value directly,
   * we record the animation.
   */
  function checkSetState(node) {
    const newState = _getStateUpdate(node);
    if (newState && newState.properties) {
      newState.properties.forEach(p => {
        const stateProperty = p.key && p.key.name;
        if (!stateProperty) {
          return;
        }
        const value = p.value;
        // If setting state to an animation directly, record the animation
        const isAnimation = astHelpers.isAnimationDeclaration(value.callee);
        if (isAnimation) {
          _updateAnimationRecord(node, stateProperty);
        } else if (p.value.type === "Identifier") {
          const allVariablesInScope = context.getScope().variables;
          allVariablesInScope.forEach(variable => {
            if (variable.name !== p.value.name) {
              return;
            }
            const isAnimatedState = _checkIsStateVariableAnimated(variable);
            if (isAnimatedState) {
              _updateAnimationRecord(node, stateProperty);
            }
          });
        }
      });
    }
  }

  // Given a variable in scope, check if that variable is set to an
  // animated value at any point. (note: we don't handle the case where
  // a variable is set to an animated value but then overwritten)
  function _checkIsStateVariableAnimated(variable) {
    let isAnimated = false;
    variable.references.forEach(r => {
      // If we aren't setting the variable, skip this reference,
      // since we know it isn't setting to an animated value.
      if (!r.writeExpr) {
        return;
      }
      if (astHelpers.isAnimationDeclaration(r.writeExpr.callee)) {
        isAnimated = true;
      }
    });

    return isAnimated;
  }

  /**
   * Detect if state is being set via setState (`this.setState({foo: "bar"})`).
   * Returns the new state object.
   */
  function _getStateUpdate(node) {
    if (
      node.callee &&
      node.callee.property &&
      node.callee.property.name === "setState"
    ) {
      // We assume the first argument to setState is the new state;
      return node.arguments[0];
    }
  }

  /**
   * Record a state object property as an animation in activeAnimations.
   */
  function _updateAnimationRecord(node, stateProperty) {
    const componentId = _getParentComponentId(node);
    const componentAnimations = activeAnimations[componentId] || {};
    componentAnimations[stateProperty] = node;
    activeAnimations[componentId] = componentAnimations;
  }

  /**
   * Checks for different ways of initializing state.
   */
  function _getStateInitialization(node) {
    if (node.parent && node.parent.type === "ObjectExpression") {
      // Handle ES6 class property declaration
      const objectExpression = node.parent;
      const maybeState = objectExpression.parent;
      if (
        maybeState.type === "ClassProperty" &&
        maybeState.key.name === "state"
      ) {
        return node.key.name;
      }
      // Handle this.state = {} syntax (constructor initialization)
      if (objectExpression.parent.type === "AssignmentExpression") {
        const left = objectExpression.parent.left;
        if (
          left.object &&
          left.object.type === "ThisExpression" &&
          left.property.name === "state"
        ) {
          return node.key.name;
        }
      }
      // Handle getInitialState syntax
      let currNode = node.parent;
      while (currNode) {
        if (
          currNode.type === "FunctionExpression" &&
          currNode.parent && currNode.parent.key &&
          currNode.parent.key.name === "getInitialState"
        ) {
          return node.key.name;
        }
        currNode = currNode.parent;
      }
    }
  }

  /**
   * Checks for animation teardowns in componentWillUnmount
   */
  function checkComponentWillUnmountForTeardown(node) {
    if (node.key.name !== "componentWillUnmount") {
      return;
    }
    const statements = node.value.body.body;
    const stateVariables = {};
    const componentId = _getParentComponentId(node);
    statements.forEach(statement => {
      const isTeardown = astHelpers.isAnimationTeardown(statement);
      const extractedState = _getStateExtraction(statement, stateVariables);
      if (extractedState) {
        stateVariables[extractedState.variable] = extractedState.property;
      }
      if (isTeardown) {
        const statePropertyName = astHelpers.getTornDownAnimationState(
          statement
        );
        // If we're directly tearing down from a state reference
        // (e.g. this.state.foo.stopAnimation(), mark it directly.
        if (statePropertyName) {
          const componentAnimations = activeAnimations[componentId];
          if (componentAnimations) {
            delete activeAnimations[componentId][statePropertyName];
          }
        } else {
          // Otherwise, trace the variable to determine if it
          // corresponds to any of the variables extracted from state
          const torndownVariable = statement.expression.callee.object;
          const stateMatch = stateVariables[torndownVariable.name];
          if (torndownVariable.type === "Identifier" && stateMatch) {
            const componentAnimations = activeAnimations[componentId];
            if (componentAnimations) {
              delete activeAnimations[componentId][stateMatch];
            }
          }
        }
      }
    });
  }

  // Aggregate cases where state is extracted into variables.
  // Can take the form of either const {color} = this.state;
  // or const hue = this.state.color;
  function _getStateExtraction(statement, stateVariables) {
    if (statement && statement.type === "VariableDeclaration") {
      statement.declarations.forEach(declaration => {
        // Handle `const {color} = this.state;` case
        if (declaration.id.type === "ObjectPattern") {
          declaration.id.properties.forEach(prop => {
            stateVariables[prop.key.name] = prop.key.name;
          });
          // Handle `const hue = this.state.color;` case
        } else if (
          declaration.id.type === "Identifier" &&
          declaration.init.property
        ) {
          const propertyName = declaration.init.property.name;
          stateVariables[declaration.id.name] = propertyName;
        }
      });
    }
  }

  /**
   * Traverse up the tree to find the parent component
   */
  function _getParentComponent(node) {
    let currNode = node;
    while (currNode) {
      // Handle ES6 class syntax
      if (currNode.type === "ClassDeclaration") {
        return currNode;
      }
      // Handle React.createClass syntax
      if (currNode.type === "CallExpression" && currNode.callee) {
        const expression = currNode.callee;
        if (
          expression.object.name === "React" &&
          expression.property.name === "createClass"
        ) {
          return currNode.parent;
        }
      }
      currNode = currNode.parent;
    }
  }

  // Traverse up the tree to find parent component's ID
  function _getParentComponentId(node) {
    const component = _getParentComponent(node);
    return getComponentId(component);
  }

  // Return a unique identifer for the provided react component.
  function getComponentId(node) {
    const componentName = node.id.name;
    const { start, end } = node;
    return `${componentName}:${start}:${end}`;
  }

  // Determine whether Animated is imported from react-native
  // (using the require() import syntax)
  function isReactNativeAnimationRequireImport(node) {
    // extract left and right of a variable declaration like
    // {Animated} = require('my-animation-library')
    const left = node.id;
    const right = node.init;
    if (left.type === "ObjectPattern") {
      const propertyNames = left.properties.map(p => p.key && p.key.name);
      if (propertyNames.indexOf("Animated") === -1) {
        return;
      }
    }
    if (left.type === "Identifier" && left.name !== "Animated") {
      return;
    }
    const requireImport =
      right && right.callee && right.callee.name === "require";
    const required = requireImport && right.arguments[0].value;
    if (requireImport && required === "react-native") {
      return;
    }
    unexpectedImport = true;
  }

  // Detect if Animated is imported from an unusual source (not
  // react-native) via standard import syntax
  function isReactNativeAnimationImport(node) {
    if (node.specifiers.length == 0) {
      return;
    }
    const specifier = node.specifiers[0];
    if (
      specifier &&
      specifier.local.name === "Animated" &&
      node.source.value !== "react-native"
    ) {
      unexpectedImport = true;
    }
  }

  return {
    MethodDefinition: node => {
      // componentWillUnmount can be a method
      checkComponentWillUnmountForTeardown(node);
    },

    Property: node => {
      // componentWillUnmount can be a property
      checkComponentWillUnmountForTeardown(node);
      // Animation state can be declared as an object property
      checkAnimatedStateInitialization(node);
    },

    CallExpression: node => {
      // Animation state can also be set via setState
      checkSetState(node);
    },

    VariableDeclarator: node => {
      isReactNativeAnimationRequireImport(node);
    },

    ImportDeclaration: node => {
      isReactNativeAnimationImport(node);
    },

    "Program:exit": () => {
      reportMissingTeardowns();
    }
  };
};

module.exports = {
  meta: {
    docs: {
      description: "Teardown animations in `componentWillUnmount`",
      category: "react-native",
      recommended: true
    }
  },
  create
};
