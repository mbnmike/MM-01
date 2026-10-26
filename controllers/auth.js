const { response } = require("express"); // destructuring

const login = async (req, res = response) => {
    const { email, password } = req.body;

    // search the user in a database
    //throw an error if not founds
    if(password != "1234"){
        return res.status(400).json({
            msg: " Password is incorrect"
        });
    }

    res.json({
        name:"test",
        token: " JWT Token",
        msg:"Successsfully logged in"
    });
};

module.exports = { 
    login,
 };