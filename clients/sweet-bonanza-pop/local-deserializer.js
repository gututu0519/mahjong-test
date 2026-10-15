/* Use the client's offline deserialization path for captured component data.
 * The online branch requires a signed, expiring origin/session configuration.
 * Limit the flag to this synchronous call; gameplay stays in normal UI mode.
 */
(() => {
  // The captured mobile client auto-enters fullscreen using an obsolete argument.
  // In the lobby, the outer player's fullscreen button owns that interaction.
  if (window.top !== window && window.FullScreenManager) {
    FullScreenManager.RequestFullscreen = function () {};
  }
  const deserialize = window.deserializeComponentRec;
  if (typeof deserialize !== 'function') throw new Error('Unsupported PP client build');
  window.deserializeComponentRec = function (...args) {
    const config = window.UHT_GAME_CONFIG_SRC;
    const hadFlag = Object.prototype.hasOwnProperty.call(config, 'replayMode');
    const previous = config.replayMode;
    config.replayMode = true;
    try { return deserialize.apply(this, args); }
    finally {
      if (hadFlag) config.replayMode = previous;
      else delete config.replayMode;
    }
  };
})();
