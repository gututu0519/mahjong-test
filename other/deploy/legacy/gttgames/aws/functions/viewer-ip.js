function handler(event) {
    var request = event.request;
    request.headers['x-gtt-client-ip'] = {value: event.viewer.ip};
    return request;
}
