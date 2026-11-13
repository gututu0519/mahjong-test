(() => {
  if (!['/sss-jf2/', '/sss-tbv/', '/mpt2/', '/rx10000/'].some(path => location.pathname.startsWith(path))) return;
  const emit = event => { try { Promise.resolve(window.__captureDecoded(event)).catch(() => {}); } catch {} };
  let system;
  const installed = new WeakSet();
  function install(value) {
    if (!value || typeof value.register !== 'function' || installed.has(value)) return;
    installed.add(value);
    const wrap = register => function (...args) {
      const name = args[0], factory = args[args.length - 1];
      if (typeof name === 'string' && name.includes('/WASM-') && typeof factory === 'function') {
        args[args.length - 1] = function (publish, context) {
          return factory(function (key, value) {
            const exports = typeof key === 'object' ? {...key} : {[key]: value};
            const commandKey = name === 'chunks:///WASM-80e4c733.js' ? 'b'
              : ['chunks:///WASM-b0a7e8f0.js', 'chunks:///WASM-fb1f222b.js'].includes(name) ? 'c' : null;
            if (commandKey && typeof exports[commandKey] === 'function') {
              const command = exports[commandKey];
              exports[commandKey] = function (...input) {
                const result = command.apply(this, input);
                if (input[0] === 0) {
                  const request = Array.from(input[1] || []);
                  Promise.resolve(result).then(response => emit({kind:'spin', request,
                    response:{type:response.type, ret:response.ret, data:Array.from(response.data || [])}}),
                    error => emit({kind:'spin-error', error:String(error)}));
                }
                return result;
              };
              emit({kind:'ready'});
            }
            return typeof key === 'object' ? publish(exports) : publish(key, exports[key]);
          }, context);
        };
      }
      return register.apply(this, args);
    };
    // SystemJS installs named-register on its prototype after assigning window.System.
    // Resolve that method dynamically instead of shadowing the unfinished loader.
    let assigned = Object.prototype.hasOwnProperty.call(value, 'register') ? value.register : null;
    let last, wrapped;
    Object.defineProperty(value, 'register', {configurable:true,
      get(){const current=assigned || Object.getPrototypeOf(value).register;
        if(current!==last){last=current;wrapped=wrap(current)}return wrapped;},
      set(next){assigned=next;}
    });
  }
  const previous = window.System;
  Object.defineProperty(window, 'System', {configurable:true, get(){return system},
    set(value){system=value;install(value);}});
  window.System = previous;
})();
