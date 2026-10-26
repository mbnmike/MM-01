const express = require("express");
const cors = require("cors");
const path = require("path");

class Server{
    constructor(){
        this.app = express();
        this.app.use(express.json())
        this.port = process.env.PORT; // loaded from .env file
        this.paths = {
            auth:"/api/auth",
            homepage:"/api/homepage",
        };

        this.middlewares();
        this.routes();
    }

    middlewares(){
        this.app.use(cors()); // enable CORS
    }

    // Bind controllers to routes
    routes(){
        this.app.use(this.paths.auth, require("../routes/auth"));
        this.app.use(this.paths.homepage, require("../routes/homepage"));
    }

    listen(){
        this.app.listen(this.port, ()=>{
            console.log("Server running on port: ", this.port);
        });
    }
}

module.exports = Server;