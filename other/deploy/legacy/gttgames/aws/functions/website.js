function handler(event) {
    var request = event.request;
    if (request.headers.host.value !== 'www.${DomainName}') {
        return request;
    }
    var parts = [];
    var query = request.querystring || {};
    Object.keys(query).forEach(function (key) {
        var item = query[key];
        var values = item.multiValue || [item];
        values.forEach(function (value) {
            parts.push(key + '=' + value.value);
        });
    });
    var suffix = parts.length ? '?' + parts.join('&') : '';
    return {
        statusCode: 308,
        statusDescription: 'Permanent Redirect',
        headers: {location: {value: 'https://${DomainName}' + request.uri + suffix}}
    };
}
