System.register([], function (_export, _context) {
  "use strict";

  var cc, Application;

  function _classCallCheck(instance, Constructor) { if (!(instance instanceof Constructor)) { throw new TypeError("Cannot call a class as a function"); } }

  function _defineProperties(target, props) { for (var i = 0; i < props.length; i++) { var descriptor = props[i]; descriptor.enumerable = descriptor.enumerable || false; descriptor.configurable = true; if ("value" in descriptor) descriptor.writable = true; Object.defineProperty(target, descriptor.key, descriptor); } }

  function _createClass(Constructor, protoProps, staticProps) { if (protoProps) _defineProperties(Constructor.prototype, protoProps); if (staticProps) _defineProperties(Constructor, staticProps); return Constructor; }

  return {
    setters: [],
    execute: function () {
      _export("Application", Application = /*#__PURE__*/function () {
        function Application() {
          _classCallCheck(this, Application);
        }

        _createClass(Application, [{
          key: "init",
          value: function init(engine) {
            cc = engine;
            cc.game.onPostProjectInitDelegate.add(this.onPostProjectInit.bind(this));
            window.pageLoadTiming.logTime('log851');
            window.pageLoadTiming.calculateDuration(851, 'headStartTime', 'log851');
          }
        }, {
          key: "onPostProjectInit",
          value: function onPostProjectInit() {
            cc.view.resizeWithBrowserSize(true);
          }
        }, {
          key: "GetLinkParameterByName",
          value: function GetLinkParameterByName(name) {
            var url = window.location.href;
            name = name.replace(/[\[\]]/g, '\\$&');
            var regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)'),
                results = regex.exec(url);
            if (!results) return null;
            if (!results[2]) return '';
            return decodeURIComponent(results[2].replace(/\+/g, ' '));
          }
        }, {
          key: "start",
          value: function start() {
            function getChromeVersion() {
              var raw = navigator.userAgent.match(/Chrom(e|ium)\/([0-9]+)\./);
              return raw ? parseInt(raw[2], 10) : -1;
            }

            if (cc.sys.isBrowser && cc.sys.isMobile && cc.sys.os === cc.sys.OS.ANDROID) {
              if (getChromeVersion() >= 120) {
                console.log('Disable WebGL2 rendering of chrome v.120.');
                window.WebGL2RenderingContext = null;
              }
            }

            window.pageLoadTiming.logTime('log852');
            window.pageLoadTiming.calculateDuration(852, 'headStartTime', 'log852');
            window.SetProgressInterval(30);
            window.__loadStage = 'engine_init'; // 鍙湁鍟熺敤鐨勯亰鎴诧紙index.ejs 鐨� ENABLE_GAME_IDS锛夋墠鍋氬け鏁楀洖鍫辫垏閲嶆暣锛屽叾浠栭亰鎴茬董鎸佸師琛岀偤
            // 鍗′綇閫炬檪鏀圭敱 index.ejs 鐨勭湅闁€鐙楃当涓€铏曠悊

            var isGuard = !!window.IsLoadErrorReportGame;
            var RETRY_KEY = 'slotEngineInitRetry';
            var MAX_RETRY = 1;

            var getRetryCount = function getRetryCount() {
              try {
                return parseInt(sessionStorage.getItem(RETRY_KEY) || '0', 10) || 0;
              } catch (e) {
                return MAX_RETRY;
              }
            };

            var setRetryCount = function setRetryCount(n) {
              try {
                n > 0 ? sessionStorage.setItem(RETRY_KEY, String(n)) : sessionStorage.removeItem(RETRY_KEY);
              } catch (e) {}
            };

            return cc.game.init({
              settingsPath: 'src/settings.12f4a.json',
              overrideSettings: {
                splashScreen: {
                  enabled: false
                }
              }
            }).then(function () {
              window.__loadStage = 'engine_ready';

              if (cc.sys.isBrowser) {
                if (cc.gfx.deviceManager.gfxDevice instanceof cc.WebGLDevice) {
                  var device = cc.gfx.deviceManager.gfxDevice;
                  device.extensions.useVAO = false;
                }
              }

              window.SetProgressInterval(50);
              window.pageLoadTiming.logTime('log853');
              window.pageLoadTiming.calculateDuration(853, 'headStartTime', 'log853');
              cc.game.run(); // 鏀惧湪 run 涔嬪緦锛歳un 鑻ユ寔绾屾媼閷篃涓嶆渻鐒￠檺閲嶆暣

              setRetryCount(0);
            })["catch"](function (err) {
              if (!isGuard) {
                throw err;
              }

              var retry = getRetryCount();
              window.ReportLoadError && window.ReportLoadError('init_fail', 'retry=' + retry + ' ' + (err && (err.stack || err.message) || err));

              if (retry < MAX_RETRY) {
                setRetryCount(retry + 1); // 璁撳洖鍫辫珛姹傛湁鏅傞枔閫佸嚭鍐嶉噸鏁达紱妯欒鐐鸿嚜鍕曢噸鏁达紝index.ejs 涓嶆渻鐣舵垚鐜╁闆㈤枊

                window.__loadReloading = true;
                setTimeout(function () {
                  return location.reload();
                }, 500);
              }
            });
          }
        }]);

        return Application;
      }());
    }
  };
});