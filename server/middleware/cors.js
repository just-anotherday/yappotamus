const cors = require('cors');

module.exports = function (options) {
    return async (req, res, next) => {
        res.header('Access-Control-Allow-Origin', options.origin);
        res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE');
        res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
        
        if (req.method === 'OPTIONS') {
            res.status(200).end();
            return;
        }
        
        next();
    };
};