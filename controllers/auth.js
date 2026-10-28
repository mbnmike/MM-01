const { response } = require("express"); // destructuring
const bcrypt = require("bcryptjs");
const { pool } = require("../database/config");

const login = async (req, res = response) => {
    const { email, password } = req.body;

    try {
        const { rows } = await pool.query(
            "SELECT id, name, password_hash FROM users WHERE email = $1",
            [email]
        );
        const user = rows[0];

        if(!user || !(await bcrypt.compare(password, user.password_hash))){
            return res.status(400).json({
                msg: "Email or password is incorrect"
            });
        }

        res.json({
            name: user.name,
            token: " JWT Token",
            msg:"Successsfully logged in"
        });
    } catch (err) {
        console.error(err);
        res.status(500).json({
            msg: "Something went wrong, please try again"
        });
    }
};

module.exports = { 
    login,
 };
