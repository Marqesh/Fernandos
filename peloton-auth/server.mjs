// Minimal standalone account whitelist. Node 24+ (node:sqlite). No npm dependencies.
import { createServer } from "node:http";
import { DatabaseSync } from "node:sqlite";
import { randomBytes, randomUUID, scryptSync, timingSafeEqual, createHash } from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import readline from "node:readline/promises";

const COOKIE = "peloton_session";
const TTL = 7 * 24 * 60 * 60 * 1000;
const userOk = x => typeof x === "string" && /^[A-Za-z0-9_-]{3,32}$/.test(x);
const passOk = x => typeof x === "string" && x.length >= 10 && x.length <= 128;
const linkOk = x => x == null || (typeof x === "string" && x.length >= 1 && x.length <= 120);
const sha256 = x => createHash("sha256").update(x).digest("hex");
const derive = (password,salt) => scryptSync(password,Buffer.from(salt,"hex"),64,{N:32768,r:8,p:1,maxmem:64*1024*1024});
function passwordHash(password) {
  const salt = randomBytes(16).toString("hex");
  return {salt, hash:derive(password,salt).toString("hex")};
}
function passwordMatches(password, account) {
  const expected = Buffer.from(account?.hash || "00".repeat(64),"hex");
  const actual = derive(password, account?.salt || "00".repeat(16));
  return expected.length === actual.length && timingSafeEqual(expected,actual);
}
function reply(res, status, body) {
  res.writeHead(status,{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store","X-Content-Type-Options":"nosniff"});
  res.end(JSON.stringify(body));
}
async function readJson(req) {
  if (!req.headers["content-type"]?.startsWith("application/json")) throw {status:415,message:"JSON required."};
  let data="";
  for await(const chunk of req) {
    data+=chunk.toString("utf8");
    if(Buffer.byteLength(data)>8192) throw {status:413,message:"Request too large."};
  }
  try {
    const val=JSON.parse(data || "{}");
    if(!val || typeof val!=="object" || Array.isArray(val)) throw Error();
    return val;
  } catch {throw {status:400,message:"Invalid JSON."};}
}
function cookieToken(req) {
  return (req.headers.cookie || "").match(/(?:^|;\s*)peloton_session=([A-Za-z0-9_-]+)/)?.[1] || null;
}
export function makeAuth({dbPath=process.env.PELOTON_AUTH_DB || "./private/peloton-auth.sqlite",
                       origin=process.env.APP_ORIGIN || null,
                       secure=process.env.NODE_ENV==="production"}={}) {
  if(process.env.NODE_ENV==="production" && !origin) throw Error("APP_ORIGIN required in production.");
  mkdirSync(dirname(resolve(dbPath)),{recursive:true,mode:0o700});
  const db=new DatabaseSync(resolve(dbPath));
  db.exec("PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL;");
  db.exec("CREATE TABLE IF NOT EXISTS accounts ("+
    "id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL COLLATE NOCASE, salt TEXT NOT NULL, "+
    "hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'player' CHECK(role IN ('admin','player')), "+
    "approved INTEGER NOT NULL DEFAULT 0 CHECK(approved IN (0,1)), "+
    "enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)), "+
    "road_player_id TEXT UNIQUE, cyclocross_player_id TEXT UNIQUE, "+
    "must_change_password INTEGER NOT NULL DEFAULT 1 CHECK(must_change_password IN (0,1)));"+
    "CREATE TABLE IF NOT EXISTS sessions ("+
    "token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, "+
    "expires_at INTEGER NOT NULL); CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(account_id);");
  // Upgrade databases created before the first-login password-change requirement.
  // Existing accounts are forced to choose their own private password once.
  if(!db.prepare("PRAGMA table_info(accounts)").all().some(x=>x.name==="must_change_password")) {
    db.exec("ALTER TABLE accounts ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 1 CHECK(must_change_password IN (0,1));");
  }
  const fields="id,username,role,approved,enabled,road_player_id,cyclocross_player_id,must_change_password";
  const safe = a => a && ({id:a.id,username:a.username,role:a.role,
    roadPlayerId:a.road_player_id,cyclocrossPlayerId:a.cyclocross_player_id,
    mustChangePassword:!!a.must_change_password});
  const failures=new Map();
  function add({username,password,role="player",approved=false,roadPlayerId=null,cyclocrossPlayerId=null}) {
    if(!userOk(username)||!passOk(password)||!linkOk(roadPlayerId)||!linkOk(cyclocrossPlayerId))
      throw {status:400,message:"Use a valid username, password (10+ chars) and player IDs."};
    if(role!=="player" && role!=="admin") throw {status:400,message:"Invalid role."};
    const id=randomUUID(), p=passwordHash(password);
    try {
      db.prepare("INSERT INTO accounts(id,username,salt,hash,role,approved,road_player_id,cyclocross_player_id) VALUES(?,?,?,?,?,?,?,?)")
        .run(id,username,p.salt,p.hash,role,approved?1:0,roadPlayerId,cyclocrossPlayerId);
    } catch(e) {
      if(e.code?.includes("CONSTRAINT")) throw {status:409,message:"Username or linked player already used."};
      throw e;
    }
    return db.prepare("SELECT "+fields+" FROM accounts WHERE id=?").get(id);
  }
  function bootstrap(username,password) {
    if(db.prepare("SELECT COUNT(*) n FROM accounts WHERE role='admin'").get().n)
      throw Error("Admin already exists; bootstrap is disabled.");
    return safe(add({username,password,role:"admin",approved:true}));
  }
  function current(req) {
    const token=cookieToken(req);
    if(!token) return null;
    return db.prepare("SELECT a.* FROM accounts a JOIN sessions s ON a.id=s.account_id "+
      "WHERE s.token_hash=? AND s.expires_at>? AND a.approved=1 AND a.enabled=1")
      .get(sha256(token),Date.now()) || null;
  }
  function setCookie(res,token,maxAge) {
    res.setHeader("Set-Cookie",COOKIE+"="+token+"; Path=/; HttpOnly; SameSite=Lax; Max-Age="+
      maxAge+(secure?"; Secure":""));
  }
  async function handler(req,res) {
    const path=new URL(req.url,"http://localhost").pathname;
    if(!path.startsWith("/api/auth/")) return reply(res,404,{error:"Not found."});
    if(!["GET","HEAD"].includes(req.method) && origin && req.headers.origin &&
       req.headers.origin!==origin) return reply(res,403,{error:"Origin not allowed."});
    try {
      if(path==="/api/auth/login" && req.method==="POST") {
        const {username,password}=await readJson(req);
        if(!userOk(username)||typeof password!=="string"||password.length>128)
          return reply(res,401,{error:"Invalid username or password."});
        const key=(req.socket.remoteAddress || "unknown")+":"+username.toLowerCase();
        const st=failures.get(key) || {n:0,until:0};
        if(st.until<=Date.now()){st.n=0;st.until=Date.now()+15*60*1000;}
        if(st.n>=5) return reply(res,429,{error:"Too many attempts; try later."});
        const found=db.prepare("SELECT * FROM accounts WHERE username=? COLLATE NOCASE").get(username);
        const valid=passwordMatches(password,found);
        if(!valid || !found.approved || !found.enabled) {
          st.n++;failures.set(key,st);
          return reply(res,401,{error:"Invalid username or password."});
        }
        failures.delete(key);
        const token=randomBytes(32).toString("base64url");
        db.prepare("INSERT INTO sessions(token_hash,account_id,expires_at) VALUES(?,?,?)")
          .run(sha256(token),found.id,Date.now()+TTL);
        setCookie(res,token,Math.floor(TTL/1000));
        return reply(res,200,{member:safe(found)});
      }
      if(path==="/api/auth/logout" && req.method==="POST") {
        const token=cookieToken(req);
        if(token) db.prepare("DELETE FROM sessions WHERE token_hash=?").run(sha256(token));
        setCookie(res,"",0);
        return reply(res,200,{ok:true});
      }
      const me=current(req);
      if(path==="/api/auth/me" && req.method==="GET")
        return reply(res,200,{member:safe(me) || null});
      if(!me) return reply(res,401,{error:"Log in first."});
      // A temporary password cannot be used to access the league or admin functions.
      // This endpoint is the only action permitted until the owner sets a private one.
      if(path==="/api/auth/change-password" && req.method==="POST") {
        const {currentPassword,newPassword}=await readJson(req);
        if(typeof currentPassword!=="string" || !passOk(newPassword))
          return reply(res,400,{error:"Current password and a new password (10-128 characters) are required."});
        if(!passwordMatches(currentPassword,me))
          return reply(res,403,{error:"Current password is incorrect."});
        if(passwordMatches(newPassword,me))
          return reply(res,400,{error:"New password must differ from your temporary password."});
        const next=passwordHash(newPassword);
        // Revoke all old sessions and issue a new session after the password is changed.
        const token=randomBytes(32).toString("base64url");
        db.exec("BEGIN IMMEDIATE");
        try {
          db.prepare("UPDATE accounts SET salt=?, hash=?, must_change_password=0 WHERE id=?")
            .run(next.salt,next.hash,me.id);
          db.prepare("DELETE FROM sessions WHERE account_id=?").run(me.id);
          db.prepare("INSERT INTO sessions(token_hash,account_id,expires_at) VALUES(?,?,?)")
            .run(sha256(token),me.id,Date.now()+TTL);
          db.exec("COMMIT");
        } catch(error) {
          db.exec("ROLLBACK");
          throw error;
        }
        setCookie(res,token,Math.floor(TTL/1000));
        return reply(res,200,{member:safe(db.prepare("SELECT * FROM accounts WHERE id=?").get(me.id))});
      }
      if(me.must_change_password) return reply(res,403,{error:"Password change required."});
      if(me.role!=="admin") return reply(res,403,{error:"Admin only."});

      if(path==="/api/auth/admin/users" && req.method==="GET") {
        const users=db.prepare("SELECT "+fields+" FROM accounts ORDER BY username").all()
          .map(a=>({...safe(a),approved:!!a.approved,enabled:!!a.enabled}));
        return reply(res,200,{users});
      }
      if(path==="/api/auth/admin/users" && req.method==="POST") {
        const body=await readJson(req);
        // Creation does not auto-approve accounts unless admin deliberately selects approve.
        const account=add({username:body.username,password:body.password,role:"player",
          approved:body.approved===true,roadPlayerId:body.roadPlayerId ?? null,
          cyclocrossPlayerId:body.cyclocrossPlayerId ?? null});
        return reply(res,201,{member:safe(account)});
      }
      const match=path.match(/^\/api\/auth\/admin\/users\/([0-9a-f-]{36})$/i);
      if(match && req.method==="PATCH") {
        const id=match[1], body=await readJson(req);
        const target=db.prepare("SELECT * FROM accounts WHERE id=?").get(id);
        if(!target) return reply(res,404,{error:"User not found."});
        if((body.enabled!==undefined && typeof body.enabled!=="boolean")||
           (body.approved!==undefined && typeof body.approved!=="boolean")||
           (body.roadPlayerId!==undefined && !linkOk(body.roadPlayerId))||
           (body.cyclocrossPlayerId!==undefined && !linkOk(body.cyclocrossPlayerId)))
          return reply(res,400,{error:"Invalid update."});
        if(id===me.id && (body.enabled===false || body.approved===false))
          return reply(res,400,{error:"Cannot disable your own admin account."});
        try {
          db.prepare("UPDATE accounts SET approved=?, enabled=?, road_player_id=?, cyclocross_player_id=? WHERE id=?")
            .run(body.approved===undefined?target.approved:Number(body.approved),
                 body.enabled===undefined?target.enabled:Number(body.enabled),
                 body.roadPlayerId===undefined?target.road_player_id:body.roadPlayerId,
                 body.cyclocrossPlayerId===undefined?target.cyclocross_player_id:body.cyclocrossPlayerId,id);
        } catch(e) {
          if(e.code?.includes("CONSTRAINT"))
            return reply(res,409,{error:"Player ID already belongs to another account."});
          throw e;
        }
        if(body.approved===false || body.enabled===false)
          db.prepare("DELETE FROM sessions WHERE account_id=?").run(id);
        return reply(res,200,{member:safe(db.prepare("SELECT "+fields+" FROM accounts WHERE id=?").get(id))});
      }
      const pw=path.match(/^\/api\/auth\/admin\/users\/([0-9a-f-]{36})\/password$/i);
      if(pw && req.method==="POST") {
        const body=await readJson(req);
        if(!passOk(body.password)) return reply(res,400,{error:"Password needs 10-128 characters."});
        const hash=passwordHash(body.password);
        const done=db.prepare("UPDATE accounts SET salt=?, hash=?, must_change_password=1 WHERE id=?")
          .run(hash.salt,hash.hash,pw[1]);
        if(!done.changes) return reply(res,404,{error:"User not found."});
        db.prepare("DELETE FROM sessions WHERE account_id=?").run(pw[1]);
        return reply(res,200,{ok:true});
      }
      return reply(res,404,{error:"Not found."});
    } catch(e) {
      if(e.status) return reply(res,e.status,{error:e.message});
      console.error("Peloton auth error",e);
      return reply(res,500,{error:"Internal server error."});
    }
  }
  return {handler,bootstrap,close:()=>db.close()};
}
if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const app=makeAuth();
  if(process.argv[2]==="bootstrap-admin") {
    const rl=readline.createInterface({input:process.stdin,output:process.stdout});
    try {
      const password=await rl.question("Initial admin password (10+ characters): ");
      const admin=app.bootstrap(process.argv[3],password);
      console.log("Created admin:",admin.username);
    } finally {rl.close();app.close();}
  } else {
    const port=Number(process.env.PORT || 3001);
    const server=createServer(app.handler);
    server.listen(port,"127.0.0.1",()=>console.log("Peloton auth on http://127.0.0.1:"+port));
    process.on("SIGTERM",()=>server.close(()=>{app.close();process.exit(0);}));
  }
}
