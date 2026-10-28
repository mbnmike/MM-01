require("dotenv").config();

const fs = require("fs");
const path = require("path");
const bcrypt = require("bcryptjs");
const { pool } = require("./config");

const setup = async () => {
    const schema = fs.readFileSync(path.join(__dirname, "schema.sql"), "utf8");
    await pool.query(schema);

    const passwordHash = await bcrypt.hash("1234", 10);
    await pool.query(
        `INSERT INTO users (name, email, password_hash)
         VALUES ($1, $2, $3)
         ON CONFLICT (email) DO NOTHING`,
        ["test", "test@example.com", passwordHash]
    );

    console.log("Database ready. Demo user: test@example.com / 1234");
};

setup()
    .catch((err) => {
        console.error(err);
        process.exitCode = 1;
    })
    .finally(() => pool.end());
