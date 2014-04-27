import MySQLdb
global db,count,MySQL
db = MySQLdb.connect("127.0.0.1", "user", "password", "database")
count = 0
MySQL = MySQLdb

def on_share(job_id, worker_name, init_time, dif):
	global count,db
	if count > 100:
		log.info("Reconnecting to the mysql socket")
		db = MySQL.connect("127.0.0.1", "user", "password", "database")
		count = 0
	dbc = db.cursor()
	count += 1
	r = dbc.execute("update blabla")
	db.commit()
	log.info("Saving share of size %s for %s/%s (%d)" %(dif,worker_name,wid,r))
