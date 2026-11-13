System.register([], function (_export, _context) {
  "use strict";

  var Application, cc;
  _export("Application", void 0);
  return {
    setters: [],
    execute: function () {
      _export("Application", Application = class Application {
        init(engine) {
          cc = engine;
          cc.game.onPostProjectInitDelegate.add(this.onPostProjectInit.bind(this));
        }
        onPostProjectInit() {
          cc.view.resizeWithBrowserSize(true);
        }
        GetLinkParameterByName(name) {
          var url = window.location.href;
          name = name.replace(/[\[\]]/g, '\\$&');
          var regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)'),
            results = regex.exec(url);
          if (!results) return null;
          if (!results[2]) return '';
          return decodeURIComponent(results[2].replace(/\+/g, ' '));
        }
        start() {
          // 手機上關閉 WEBGL_ANTIALIAS (巨集設定)
          if (cc.sys.isBrowser && cc.sys.isMobile) {
            cc.macro.ENABLE_WEBGL_ANTIALIAS = false;
          }
          window.SetProgressInterval(30);
          return cc.game.init({
            settingsPath: 'src/settings.e5355.json',
            overrideSettings: {
              splashScreen: {
                enabled: false
              }
            },
            debugMode: cc.DebugMode.ERROR
          }).then(() => {
            if (cc.sys.isBrowser) {
              // 調整動態合圖最大數量
              if (cc.sys.isMobile) {
                cc.dynamicAtlasManager.maxAtlasCount = 2;
              }
              cc.assetManager.downloader.maxConcurrency = 15;
              cc.assetManager.downloader.maxRequestsPerFrame = 64;
            }
            window.SetProgressInterval(50);
            cc.game.run();
          });
        }
      });
    }
  };
});