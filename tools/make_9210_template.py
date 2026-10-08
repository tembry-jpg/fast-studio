import json, pikepdf
U="/root/.claude/uploads/13562657-4794-5c75-a24c-05caf49f3ed3/"
ONE=U+"d397f819-9210-02-1up.pdf"; MASS=U+"dcd03e19-9210-02_-_Mass_Export.pdf"
SHIFT=600.0
out=pikepdf.new()
one=pikepdf.open(ONE); mass=pikepdf.open(MASS)
# page 1: the 1-up raised by SHIFT on a taller page (room for the info panel)
src=one.pages[0]
out.pages.append(src)
pg=out.pages[0]
mb=[float(v) for v in pg.MediaBox]; W,H=mb[2]-mb[0],mb[3]-mb[1]
pre=out.make_stream(b"q 1 0 0 1 0 %.2f cm\n"%SHIFT); post=out.make_stream(b"\nQ\n")
c=pg.obj.Contents
arr=pikepdf.Array([pre]+(list(c) if isinstance(c,pikepdf.Array) else [c])+[post])
pg.obj.Contents=arr
pg.obj.MediaBox=pikepdf.Array([0,0,W,H+SHIFT])
for k in ("/CropBox","/TrimBox","/ArtBox","/BleedBox"):
    if k in pg.obj: del pg.obj[k]
for p in mass.pages: out.pages.append(p)
out.save("press/9210-02-1C.pdf")
print("1-up",W,H)
# zones (1-up svg coords are top-down from the 1-up's top)
def Y(y_svg): return H-y_svg+SHIFT
z1={"cx":1168.25,"cy":Y(242.36),"w":648.0,"h":288.0,"left":844.25,"top":Y(98.36)}
z2={"cx":416.75,"cy":Y(242.36),"w":648.0,"h":288.0,"left":92.75,"top":Y(98.36)}
PH=1656.0
def P(cx,cy): return {"cx":round(cx,2),"cy":round(PH-cy,2),"gap":0.0,"vertical":True}
FRONT_DX,BACK_DX,DY=-20.25,20.25,7.86
pages={
 "2":{"artboard":"DBG FRONT","machine":"DBG","sides":["side1"],
      "positions":[P((177.7+969.6)/2+FRONT_DX,(372.9+840.9)/2+DY),P((177.7+969.6)/2+FRONT_DX,(840.9+1308.9)/2+DY)]},
 "3":{"artboard":"DBG BACK","machine":"DBG","sides":["side2"],
      "positions":[P((181.0+972.85)/2+BACK_DX,(372.9+840.9)/2+DY),P((181.0+972.85)/2+BACK_DX,(840.9+1308.9)/2+DY)]},
 "4":{"artboard":"DISCO FRONT","machine":"DISCO","sides":["side1"],
      "positions":[P((180.55+972.45)/2+FRONT_DX,(594.0+1062.0)/2+DY)]},
 "5":{"artboard":"DISCO BACK","machine":"DISCO","sides":["side2"],
      "positions":[P((177.0+968.9)/2+BACK_DX,(594.0+1062.0)/2+DY)]},
}
names_at={"2":[860,1405,0],"3":[860,1405,0],"4":[860,1335,0],"5":[860,1335,0]}
for k,v in pages.items():
    v.update({"page":[1152.0,PH],"rotation":0,"name_at":names_at[k]})
spec={
 "_scope":"9210-02 Horizontal Bank Bag 10.5 x 5.5, both item numbers (9210-02-EV-1C expanded vinyl, 9210-02-LN-1C laminated nylon): one die, one template; only the material colour differs.",
 "_template_file":"9210-02-1C.pdf: page 1 = the 1-up raised 600 pt on a taller page (room for the proof's info panel); pages 2-5 = '9210-02 - Mass Export' (DBG 2-up Front, DBG 2-up Back, DISCO Front, DISCO Back).",
 "_measured_by":"1-up: vector rectangles (body 756 x 396 pt = 10.5 x 5.5 in; imprint 648 x 288 pt = 9 x 4 in, centred on the body). Sheets: the crop-mark corners of each 792 x 468 pt cell (= one 1-up panel), the imprint placed in the cell as it sits in its 1-up panel: Front 20.25 pt toward the fold, Back 20.25 pt the other way, 7.86 pt below the cell's centre (the zipper fold-in strip is on top).",
 "_unverified":"Never checked against a printed sheet: confirm the art lands in the imprint on the first DBG and DISCO sheets, and that the Front/Back sheets carry the panels the way up the 1-up shows them (zipper strip on top).",
 "template":"9210-02 - Horizontal Bank Bag","product":"9210-02-EV-1C","products":["9210-02-EV-1C","9210-02-LN-1C"],
 "guide_pages":{"1":{"sides":["side1","side2"],"zones":{"side1":z1,"side2":z2}}},
 "offsets":{"side_w":648.0,"side_h":288.0,"circle_d":0.0,"d_side1":0.0,"d_side2":0.0},
 "side2_turn":0,
 "press_pages":pages,
 "_sides_note":"Each sheet prints one panel: 'sides' says which. A job with only Side 1 gets only the Front sheets.",
 "proof_cover":[0,0,0,0],
 "info_panel":{"x":60,"y_top":560,"w":760,"scale":1.6},
 "die_fill":[[36.18,round(H-433.5+SHIFT,2),756.0,396.0],[792.82,round(H-433.5+SHIFT,2),756.0,396.0]],
}
json.dump(spec,open("press/press_spec_9210-02.json","w"),indent=1)
print(json.dumps(pages,indent=0)[:600])
