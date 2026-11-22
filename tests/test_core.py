import sys, types, importlib.util, pathlib
from collections import namedtuple
ROOT = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "rockwell_plc"

# fake pycomm3
Tag = namedtuple("Tag", "tag value type error")
class FakeDriver:
    mem = {"Tank_Level": 523, "Pump_Run": True, "N7:0": 12, "F8:1": 3.5, "Bad": None}
    def __init__(self, path, **kw): self.path=path; self.connected=False; self.info={"product_name":"5069-L330ERMS2","revision":"33.11","name":"PLCA"}
    def open(self): self.connected=True; return True
    def close(self): self.connected=False
    def _r(self, t): return Tag(t, None, None, "Tag doesn't exist") if t not in self.mem or self.mem[t] is None else Tag(t, self.mem[t], "DINT", None)
    def read(self, *tags):
        r=[self._r(t) for t in tags]; return r[0] if len(r)==1 else r
    def write(self, tv):
        t,v=tv
        if t=="Locked": return Tag(t,v,None,"Privilege violation")
        self.mem[t]=v; return Tag(t,v,"DINT",None)
class FakeSLC(FakeDriver):
    def __init__(self, path, **kw): super().__init__(path); self.info={}
    def get_module_info(self, slot): raise RuntimeError("no backplane")
pc = types.ModuleType("pycomm3"); pc.LogixDriver=FakeDriver; pc.SLCDriver=FakeSLC; sys.modules["pycomm3"]=pc

pkg = types.ModuleType("rp"); pkg.__path__=[str(ROOT)]; sys.modules["rp"]=pkg
def load(n):
    spec=importlib.util.spec_from_file_location(f"rp.{n}", ROOT/f"{n}.py"); m=importlib.util.module_from_spec(spec); sys.modules[f"rp.{n}"]=m; spec.loader.exec_module(m); return m
const=load("const"); tags=load("tags"); plc=load("plc")

# parser
cfgs = tags.parse_tags("""
- tag: Tank_Level
  name: Tank Level
  unit: "%"
  scale: 0.1
- tag: Pump_Run
  platform: binary_sensor
- tag: Setpoint
  platform: number
  min: 0
  max: 50
- tag: Start_PB
  platform: button
- tag: Pump_Run
  platform: switch
""")
assert [c.platform for c in cfgs]==["sensor","binary_sensor","number","button","switch"]
assert cfgs[0].to_ha(523)==52.300000000000004 or abs(cfgs[0].to_ha(523)-52.3)<1e-9
assert [c.effective_platform(False) for c in cfgs]==["sensor","binary_sensor","sensor",None,"binary_sensor"]
assert [c.effective_platform(True) for c in cfgs]==["sensor","binary_sensor","number","button","switch"]
assert tags.parse_tags(tags.__dict__.get("x","")) == []
# commented-out example text (the default) parses as empty
assert tags.parse_tags("# - tag: X\n#   platform: sensor\n") == []
for bad, msg in [("- tag: A\n  platform: light","platform"),("- tag: A\n  scale: 0","scale"),("- tag: A\n- tag: A","twice"),("tag: A","list"),("- tag: A\n  colour: red","unknown"),("- name: x","required")]:
    try: tags.parse_tags(bad); raise SystemExit(f"should fail: {bad}")
    except tags.TagConfigError as e: assert msg in str(e), (msg, e)
assert tags.coerce_for_write(5.6, 3)==6 and tags.coerce_for_write(1, True) is True and tags.coerce_for_write(2, 1.0)==2.0
assert cfgs[0].to_raw(52.3) - 523 < 1e-9

# client
c = plc.PLCClient("logix","192.168.1.10")
assert c.connect()["product_name"]=="5069-L330ERMS2"
r = c.read(["Tank_Level","Pump_Run","Bad"])
assert r["Tank_Level"].value==523 and r["Pump_Run"].value is True and r["Bad"].error
assert c.read(["Tank_Level"])["Tank_Level"].value==523   # single-tag path returns Tag, not list
c.write("Setpoint", 25); assert c.read(["Setpoint"])["Setpoint"].value==25
try: c.write("Locked", 1); raise SystemExit("should reject")
except plc.PLCWriteError as e: print("rejected ok:", e)
c._driver.connected=False; assert c.read(["Tank_Level"])["Tank_Level"].value==523  # reconnects
import socket, struct, threading
def fake_eip_server():
    srv=socket.socket(); srv.bind(("127.0.0.1",0)); srv.listen(1)
    def run():
        c,_=srv.accept(); c.recv(24)
        name=b"1747-L551/C 5/05 CPU"
        item=struct.pack("<H",1)+b"\x00"*16+struct.pack("<HHHBBHI",1,0x0E,90,3,10,0x30,0xc01d6fd2)+bytes([len(name)])+name+b"\x03"
        body=struct.pack("<HHH",1,0x0C,len(item))+item
        c.sendall(struct.pack("<HHII8sI",0x63,len(body),0,0,b"\x00"*8,0)+body); c.close(); srv.close()
    threading.Thread(target=run,daemon=True).start(); return srv.getsockname()[1]
s = plc.PLCClient("slc",f"127.0.0.1:{fake_eip_server()}"); assert s.read(["N7:0","F8:1"])["F8:1"].value==3.5
assert s.info["product_name"]=="1747-L551/C 5/05 CPU" and s.info["revision"]=="3.10" and s.info["serial"]=="c01d6fd2", s.info
print("ALL TESTS PASSED")
