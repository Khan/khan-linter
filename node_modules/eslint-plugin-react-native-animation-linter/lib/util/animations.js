const astHelpers = {
  isAnimationDeclaration: function(node) {
    // Capture the "Animated" in "Animated.Value(0)"
    const objectMatch = node && node.object && node.object.name === "Animated";
    // Capture the "Value" in "Animated.Value(0)"
    const propertyMatch =
      node && node.property && node.property.name === "Value";
    return Boolean(objectMatch && propertyMatch);
  },

  // Detect an animation teardown (stopAnimation()) event.
  isAnimationTeardown: function(node) {
    return Boolean(
      node.expression &&
        node.expression.callee &&
        node.expression.callee.property &&
        node.expression.callee.property.name === "stopAnimation"
    );
  },

  // Detect state property that is being torn down.
  // e.g. in this.state.color.stopAnimation() ==> return "color".
  getTornDownAnimationState: function(node) {
    const object = node.expression.callee.object;
    return object.property && object.property.name;
  }
};

module.exports = {
  astHelpers
};
