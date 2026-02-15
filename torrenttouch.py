#!/usr/bin/env python
#	2026-02-15 Erik Johnson - EkriirkE
#	Set the timestamp of downloaded files to match that of the torrent.
#
#	libtorrent supports "mtime" entries.  If this exists use it, otherwise use the create date of the torrent itself, lastly the date added to transmission
#	also spport BEP 47 file attributes
import os

#What is the path of transmission's torrents and resume folders?
transmissionconfig=os.path.join(os.environ["HOME"],".config","transmission")
linkpad2zero=False #link pad files to /dev/zero, otherwise try to sparsify

#torrents are bencoded
def bdecode(f,t=None,stringify=False):
	v=""
	if t==None: t=f.read(1).decode()
	if t.isdigit():	#bytes
		v=t
		while (c:=f.read(1).decode())!=":": v+=c
		v=f.read(int(v))
		if stringify:
			try: return v.decode("utf-8")
			except: return v.decode("latin1")
		return v
	if t=="i":	#integer
		while (c:=f.read(1).decode())!="e": v+=c
		return int(v)
	if t=="l":	#list
		l=[]
		while True:
			c=f.read(1).decode()
			if c=="e": return l
			l.append(bdecode(f,c,stringify))
	if t=="d":	#dict
		d={}
		while True:
			c=f.read(1).decode()
			if c=="e": return d
			k=bdecode(f,c,True)
			v=bdecode(f,None,stringify)
			d[k]=v
	raise BaseException("Unexpected token: %s(%i)" % t,ord(t))

torrent=os.path.join(transmissionconfig,"torrents",os.environ["TR_TORRENT_HASH"]+".torrent")
resume=os.path.join(transmissionconfig,"resume",os.environ["TR_TORRENT_HASH"]+".resume")

#Load torrent object, and resume object - the resume file reflects any file renaming
with open(torrent,"rb") as f: tor=bdecode(f,stringify=True)
try:
	with open(resume,"rb") as f: res=bdecode(f,stringify=True)
except: res=None

#What will our default date be?
#Get the .torrent internal creation date and set the .torrent date to that
#Otherwise use the date of the file itself as the earliest date (usually the date the user added or started the .torrent
if dt:=tor.get("creation date"): os.utime(torrent,(dt,dt))
else:
	dt=os.stat(torrent).st_ctime
	if res and res["added-date"]<dt: dt=res["added-date"]

#Use the resume name if available, otherwise torrent name.  Prefer resume path over TR variable
name=(res or {}).get("name") or tor["info"]["name"]
dir=(res or {}).get("destination") or os.getenv("TR_TORRENT_DIR")

#Flatten torrent files similar to resume files
torfiles=[{**x,"path":os.path.join(name,*(x.get("path") or []))} for x in (tor["info"].get("files") or [tor["info"]])]	#If no files, treat info as 1 file.  Flatten any paths with adjacent tags

#In case there were changes in the file naming, use the "resume" metadata if available.  Assuming a 1:1 file order betwixt the torrent and resume files
if res: torfiles=[{**torfiles[i],"path":f} for i,f in enumerate(res.get("files") or [res["name"]])]

#Iterate the files
for f in torfiles:
	ff=os.path.join(dir,f["path"])
	if not os.path.exists(ff): continue
	#Are there attributes stored?
	if a:=f.get("attr"): #p)ad [sparse], h)idden, x)ecutable, l)ink
		fs=os.stat(ff)
		if "p" in a: #Ensure the file is relinked or truncated and sparsed
			os.unlink(ff)
			if linkpad2zero: os.symlink("/dev/zero",ff)
			else:
				with open(ff,"wb") as sparse: os.ftruncate(sparse,f["length"])
		if "l" in a and (l:=os.path.join(*(f.get("symlink path") or []))) and not fs.st_size: #Only generate the symlink if the file is empty
			os.unlink(ff)
			os.symlink(l,ff,os.path.isdir(l))
		if "x" in a: os.chmod(ff,fs.st_mode | 0o111)
	#Try per-file date?
	if d:=f.get("mtime"): os.utime(ff,(d,d))
	#Finally, use default date
	else: os.utime(ff,(dt,dt))
