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
  // Stop UI spin actions before they enter the animation/request state machine.
  const trigger = XT.TriggerEvent;
  XT.TriggerEvent = function (name) {
    const blocked = [Vars.Evt_DataToCode_Pressed_Spin, Vars.Evt_DataToCode_ConfirmSpinStart,
      Vars.Evt_DataToCode_StartAutoplay, Vars.Evt_ToServer_RequestSpin];
    if (!window.__LOCAL_GENERATED__ && name !== undefined && blocked.includes(name)) {
      const note = document.getElementById('local-preview-note');
      if (note) {
        note.textContent = '旋转暂未接入，可查看设置与规则 / Spins unavailable · Explore settings and rules';
        note.animate([{ background: '#8a6025' }, { background: '#201730ed' }], { duration: 1000 });
      }
      return;
    }
    return trigger.apply(this, arguments);
  };
})();
