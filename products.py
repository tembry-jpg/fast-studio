# products.py — Product configuration registry

PRODUCTS = {

"9100": {
        "label":        "Pocket Coolie - 9100",
        "template_ai":  "Master Symbol 9100.ai",
        "mockup_psd":   "Master_Mockup 9100.psd",
        "psb_layer":    "MASTER SYMBOL-9100",
        "material":     "scuba_foam",
        "has_neoprene":  False,
        "has_stitching": False,
        "proof_shape":   "cylinder",
        "proof_warp":    70,
        "page_w":       347.625,
        "page_h":       828.864,
        "template_zones": {
            "side1":  {"x": 0.138, "y": 0.061, "w": 0.725, "h": 0.304, "l": "Side 1"},
            "bottom": {"x": 0.331, "y": 0.430, "w": 0.337, "h": 0.141, "l": "Bottom"},
            "side2":  {"x": 0.138, "y": 0.635, "w": 0.725, "h": 0.304, "l": "Side 2"},
        },
        # Bleed zones = full printable area (blue dashed lines on template guide).
        # Used to compute the safe-to-bleed ratio so the proof view matches template sizing.
        "bleed_zones": {
            "side1":  {"x": 0.0997, "y": 0.0035, "w": 0.8107, "h": 0.4125},
            "bottom": {"x": 0.294,  "y": 0.413,  "w": 0.410,  "h": 0.173},
            "side2":  {"x": 0.0997, "y": 0.5775, "w": 0.8107, "h": 0.4125},
        },

	
        "art_slots": [
            {
                "id":       "side1",
                "label":    "Side 1",
                "size":     "3.5\" W × 3.5\" H",
                "left_pt":  47.99,
                "top_pt":   -50.74,
                "w_pt":     252.0,
                "h_pt":     252.0,
                "rotation": 0,
                "shape":    "rect",
            },
            {
                "id":       "bottom",
                "label":    "Bottom",
                "size":     "1.625\" diameter",
                "left_pt":  114.91,
                "top_pt":   -356.54,
                "w_pt":     117.0,
                "h_pt":     117.0,
                "rotation": 180,
                "shape":    "circle",
            },
            {
                "id":       "side2",
                "label":    "Side 2",
                "size":     "3.5\" W × 3.5\" H",
                "left_pt":  47.99,
                "top_pt":   -526.27,
                "w_pt":     252.0,
                "h_pt":     252.0,
                "rotation": 180,
                "shape":    "rect",
            },
        ],
    },
    

# ── Add new products below ────────────────────────────────────────────────  


    "0472-4CP": {
        "label":        "Kolder Kaddy Slim Can 4CP - 0472-4cp",
        "bleed_placement": {
            "side1":  {"ox": 249, "oy": 416, "sc": 1.47, "strx": 2.17, "stry": 1.94,"warp": 100},
            "side2":  {"ox": 249, "oy": -691, "sc": 1.47, "strx": 2.17, "stry": 1.94,"warp": 100},
            "bottom": {"ox": 143, "oy": 462, "sc": 0.76, "strx": .8, "stry": 1, "warp": 0},
        },

		
        "proof_bounds": {
            "side1":  {"x": 286, "y": 227, "w": 292, "h": 675},
            "side2":  {"x": 802, "y": 227, "w": 292, "h": 675},
            "bottom": {"x": 546, "y": 934, "w": 276, "h": 276},
        },		
        "template_ai":  "mater_template-0472.ai",
        "mockup_psd":   "Master_Mockup_0472.psd",
        "psb_layer":    "MASTER SYMBOL-0472",
        "material":     "scuba_foam_4cp",
        "has_neoprene":  False,
        "has_stitching": False,
        "is_4cp":        True,
        "proof_shape":   "cylinder",
        "proof_warp":    60,
        "page_w":        320.537,
        "page_h":        1000.800,
        "template_zones": {
            "side1":  {"x": 0.1631, "y": 0.0562, "w": 0.6747, "h": 0.3243, "l": "Side 1"},
            "bottom": {"x": 0.3128, "y": 0.4396, "w": 0.3744, "h": 0.1202, "l": "Bottom"},
            "side2":  {"x": 0.1631, "y": 0.6190, "w": 0.6747, "h": 0.3245, "l": "Side 2"},
        },
        "bleed_zones": {
            "side1":  {"x": 0.1248, "y": -0.0013, "w": 0.7514, "h": 0.4318},
            "bottom": {"x": 0.257, "y":  0.424, "w": 0.488, "h": 0.151},
            "side2":  {"x": 0.1248, "y":  0.5615, "w": 0.7514, "h": 0.4318},
        },
        "art_slots": [
            {
                "id":       "side1",
                "label":    "Side 1",
                "size":     "3\" W × 4.5\" H",
                "left_pt":  51.9912,
                "top_pt":   -621.0600,
                "w_pt":     216.0,
                "h_pt":     324.0,
                "rotation": 180,
                "shape":    "rect",
            },
            {
                "id":       "bottom",
                "label":    "Bottom",
                "size":     "1.5\" diameter",
                "left_pt":  99.7072,
                "top_pt":   -440.9986,
                "w_pt":     120.335,
                "h_pt":     120.335,
                "rotation": 0,
                "shape":    "circle",
            },
            {
                "id":       "side2",
                "label":    "Side 2",
                "size":     "3\" W × 4.5\" H",
                "left_pt":  51.9912,
                "top_pt":   -56.8729,
                "w_pt":     216.0,
                "h_pt":     324.0,
                "rotation": 0,
                "shape":    "rect",
            },
        ],
    },
	
    "9100-4CP": {
        "label":        "Pocket Coolie 4CP - 9100-4cp",
        "bleed_placement": {
            "side1":  {"ox": 249, "oy": 167, "sc": 0.87, "strx": 1.33, "stry": 1.14, "warp": 80},
            "side2":  {"ox": 371, "oy": 168, "sc": 1.00, "strx": 1.63, "stry": 1.29, "warp": 100},
            "bottom": {"ox": 176, "oy": 421, "sc": 0.73, "strx": 1.00, "stry": 1.00, "warp": 0},
        },
        "proof_bounds": {
            "side1":  {"x": 259, "y": 327, "w": 364, "h": 543},
            "side2":  {"x": 745, "y": 327, "w": 364, "h": 543},
            "bottom": {"x": 507, "y": 866, "w": 337, "h": 338},
        },
        "template_ai":  "Master Symbol 9100.ai",
        "mockup_psd":   "Master_Mockup 9100.psd",
        "psb_layer":    "MASTER SYMBOL-9100",
        "material":     "scuba_foam_4cp",
        "has_neoprene":  False,
        "has_stitching": False,
        "is_4cp":        True,   # full-bleed sublimation
        "proof_shape":   "cylinder",
        "proof_warp":    70,
        "page_w":        347.625,
        "page_h":        832.068,
        "template_zones": {
            "side1":  {"x": 0.138, "y": 0.061, "w": 0.725, "h": 0.304, "l": "Side 1"},
            "bottom": {"x": 0.331, "y": 0.430, "w": 0.337, "h": 0.141, "l": "Bottom"},
            "side2":  {"x": 0.138, "y": 0.635, "w": 0.725, "h": 0.304, "l": "Side 2"},
        },
        # Full bleed zone — full page
        "bleed_zone_full": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        "bleed_zones": {
            "side1":  {"x": 0.0997, "y": 0.0035, "w": 0.8107, "h": 0.4125},
            "bottom": {"x": 0.294,  "y": 0.413,  "w": 0.410,  "h": 0.173},
            "side2":  {"x": 0.0997, "y": 0.5775, "w": 0.8107, "h": 0.4125},
        },
        "art_slots": [
            {
                "id":       "side1",
                "label":    "Side 1",
                "size":     "3.5\" W × 3.5\" H",
                "left_pt":  47.99,
                "top_pt":   -50.94,
                "w_pt":     252.0,
                "h_pt":     252.0,
                "rotation": 0,
                "shape":    "rect",
            },
            {
                "id":       "bottom",
                "label":    "Bottom",
                "size":     "1.625\" diameter",
                "left_pt":  114.91,
                "top_pt":   -357.92,
                "w_pt":     117.0,
                "h_pt":     117.0,
                "rotation": 180,
                "shape":    "circle",
            },
            {
                "id":       "side2",
                "label":    "Side 2",
                "size":     "3.5\" W × 3.5\" H",
                "left_pt":  47.99,
                "top_pt":   -528.30,
                "w_pt":     252.0,
                "h_pt":     252.0,
                "rotation": 180,
                "shape":    "rect",
            },
        ],
    },

    "0070-3m": {
        "label":        "Kolder Kaddy - 0070-3m",
        "template_ai":  "Master Symbol 0070.ai",
        "mockup_psd":   "Master_Mockup_0070.psd",
        "psb_layer":    "MASTER SYMBOL-0070",
        "material":     "neoprene",
        "has_neoprene":  True,
        "has_stitching": True,
        "proof_shape":   "cylinder",
        "proof_warp":    70,
        "proof_imprint_inset": {
            "side1":  0.0,
            "side2":  0.0,
            "bottom": 0.12,
        },
        "page_w":       347.625,
        "page_h":       828.864,
        "template_zones": {
            "side1":  {"x": 0.1616, "y": 0.0684, "w": 0.6835, "h": 0.2767, "l": "Side 1"},
            "bottom": {"x": 0.2896, "y": 0.4149, "w": 0.4285, "h": 0.1729, "l": "Bottom"},
            "side2":  {"x": 0.1616, "y": 0.6572, "w": 0.6835, "h": 0.2767, "l": "Side 2"},
        },
        "bleed_zones": {
            "side1":  {"x": 0.1083, "y": 0.0194, "w": 0.7884, "h": 0.3747},
            "side2":  {"x": 0.1083, "y": 0.6086, "w": 0.7884, "h": 0.3747},
            "bottom": {"x": 0.2896, "y": 0.4149, "w": 0.4285, "h": 0.1729},
        },
        "art_slots": [
            {
                "id":       "side1",
                "label":    "Side 1",
                "size":     "3\" W × 3\" H",
                "left_pt":  47.99,
                "top_pt":   -50.74,
                "w_pt":     216.0,
                "h_pt":     216.0,
                "rotation": 0,
                "shape":    "rect",
            },
            {
                "id":       "bottom",
                "label":    "Bottom",
                "size":     "1.875\" diameter",
                "left_pt":  114.91,
                "top_pt":   -356.54,
                "w_pt":     135.0,
                "h_pt":     135.0,
                "rotation": 180,
                "shape":    "circle",
            },
            {
                "id":       "side2",
                "label":    "Side 2",
                "size":     "3\" W × 3\" H",
                "left_pt":  47.99,
                "top_pt":   -526.27,
                "w_pt":     216.0,
                "h_pt":     216.0,
                "rotation": 180,
                "shape":    "rect",
            },
        ],
    },


"1080-3m": {
        "label":        "Kolder Kaddy Slim Can - 1080-3m",
        "template_ai":  "Master Symbol 1080-3m.ai",
        "mockup_psd":   "Master_Mockup_1080-3m.psd",
        "psb_layer":    "MASTER SYMBOL-1080-3m",
        "material":     "neoprene",
        "has_neoprene":  True,
        "has_stitching": True,
        "proof_shape":   "cylinder",
        "proof_warp":    30,
        "proof_imprint_inset": {
            "side1":  {"t": 0.04, "r": 0.06, "b": 0.10, "l": 0.06},
            "side2":  {"t": 0.04, "r": 0.06, "b": 0.10, "l": 0.06},
            "bottom": 0.12,
        },
        "page_w":        321.3828,
        "page_h":        989.3225,
        "template_zones": {
            "side1":  {"x": 0.1593, "y": 0.0508, "w": 0.6768, "h": 0.3354, "l": "Side 1"},
            "bottom": {"x": 0.3068, "y": 0.4370, "w": 0.3817, "h": 0.1229, "l": "Bottom"},
            "side2":  {"x": 0.1593, "y": 0.6108, "w": 0.6768, "h": 0.3354, "l": "Side 2"},
        },

        "art_slots": [
            {
                "id":       "side1",
                "label":    "Side 1",
                "size":     "2.8\" W × 4.6\" H",
                "left_pt":  61.4232,
                "top_pt":   -50.2951,
                "w_pt":     201.6,
                "h_pt":     331.2,
                "rotation": 0,
                "shape":    "rect",
            },
            {
                "id":       "bottom",
                "label":    "Bottom",
                "size":     "1.7\" diameter",
                "left_pt":  101.025,
                "top_pt":   -431.4762,
                "w_pt":     122.4,
                "h_pt":     122.4,
                "rotation": 0,
                "shape":    "circle",
            },
            {
                "id":       "side2",
                "label":    "Side 2",
                "size":     "2.8\" W × 4.6\" H",
                "left_pt":  61.4256,
                "top_pt":   -603.8574,
                "w_pt":     201.6,
                "h_pt":     331.2,
                "rotation": 180,
                "shape":    "rect",
            },
        ],
    },

  "0472": {
        "label":        "Kolder Kaddy Slim Can - 0472",
        "template_ai":  "mater_template-0472.ai",
        "mockup_psd":   "Master_Mockup_0472.psd",
        "psb_layer":    "MASTER SYMBOL-0472",
        "material":     "scuba_foam",
        "has_neoprene":  False,
        "has_stitching": False,
        "proof_shape":   "cylinder",
        "proof_warp":    60,
        "proof_imprint_inset": {          # per-slot inset as {t,r,b,l} or single float
            "side1":  {"t": 0.15, "r": 0.06, "b": 0.15, "l": 0.06},
            "side2":  {"t": 0.15, "r": 0.06, "b": 0.15, "l": 0.06},
            "bottom": 0.12,
        },
        "page_w":       320.537,
        "page_h":       1000.800,
        "template_zones": {
            "side1":  {"x": 0.1631, "y": 0.0562, "w": 0.6747, "h": 0.3243, "l": "Side 1"},
            "bottom": {"x": 0.3128, "y": 0.4396, "w": 0.3744, "h": 0.1202, "l": "Bottom"},
            "side2":  {"x": 0.1631, "y": 0.6190, "w": 0.6747, "h": 0.3245, "l": "Side 2"},
        },
        "bleed_zones": {},  # No bleed adjustment — use art zone mask directly

        "art_slots": [
            {
                "id":       "side1",
                "label":    "Side 1",
                "size":     "3\" W × 4.5\" H",
                "left_pt":  51.9912,
                "top_pt":   -621.0600,
                "w_pt":     216.0,
                "h_pt":     324.0,
                "rotation": 180,
                "shape":    "rect",
            },
            {
                "id":       "bottom",
                "label":    "Bottom",
                "size":     "1.5\" diameter",
                "left_pt":  99.7072,
                "top_pt":   -440.9986,
                "w_pt":     120.335,
                "h_pt":     120.335,
                "rotation": 0,
                "shape":    "circle",
            },
            {
                "id":       "side2",
                "label":    "Side 2",
                "size":     "3\" W × 4.5\" H",
                "left_pt":  51.9912,
                "top_pt":   -56.8729,
                "w_pt":     216.0,
                "h_pt":     324.0,
                "rotation": 0,
                "shape":    "rect",
            },
        ],
    },

    "0837": {
        "label":        "Jotter Retractable Pen - 0837",
        "template_ai":  "Master Symbol 0837.ai",
        "mockup_psd":   "Master_Mockup_0837.psd",
        "psb_layer":    "MASTER SYMBOL-0837",
        "material":     "jotter",
        "has_neoprene":  False,
        "has_stitching": False,
        "proof_shape":   "flat",
        "proof_warp":    0,
        "proof_imprint_inset": {
            "side1": {"t": 0.0, "r": 0.0, "b": 0.0, "l": 0.0},
            "side2": {"t": 0.0, "r": 0.0, "b": 0.0, "l": 0.0},
        },
        # ink_black_only: body color names (lowercase substrings) that always
        # get black ink instead of a matching color ink.
        "ink_black_only": ["gray", "white", "navy", "gold"],
        # The print file holds the pen's two sides stacked, Side 1 over Side 2
        # (two faces of the same pen). The export stamps each into the 80 boxes
        # of the Mimaki jig as its own -SIDE1 / -SIDE2 file, turned 180 deg as
        # the imprint style asks: RH (standard) turns Side 1, LH turns Side 2. Box: 308.16 x 18 pt (4.28" x 0.25"),
        # the jig's "Art Symbol".
        "page_w": 308.1572,
        "page_h": 54.0,
        "mimaki_jig": "press/mimaki/0837-jig.json",
        "template_zones": {
            # h matched to the jig box's 17.1:1 (was 0.0648, 16.5:1).
            "side1": {"x": 0.2138, "y": 0.3733, "w": 0.6127, "h": 0.0626, "l": "Side 1"},
            "side2": {"x": 0.2138, "y": 0.5780, "w": 0.6127, "h": 0.0626, "l": "Side 2"},
        },
        # proof_bounds: exact imprint strip in 1350×1350 proof canvas
        # w=749px=4.25", h=44px=0.25" (measured from imprint_areas_for_proof.png)
        "proof_bounds": {
            "side1": {"x": 350, "y": 592, "w": 749, "h": 44},
            "side2": {"x": 282, "y": 716, "w": 749, "h": 44},
        },
        "bleed_zones": {},
        "art_slots": [
            {
                "id":       "side1",
                "label":    "Side 1",
                "size":     "4.28\" W × 0.25\" H",
                "left_pt":  0.0,
                "top_pt":   0.0,
                "w_pt":     308.1572,   # the jig's imprint box
                "h_pt":     18.0,
                "rotation": 0,
                "shape":    "rect",
            },
            {
                "id":       "side2",
                "label":    "Side 2",
                "size":     "4.28\" W × 0.25\" H",
                "left_pt":  0.0,
                "top_pt":   -36.0,
                "w_pt":     308.1572,
                "h_pt":     18.0,
                "rotation": 0,
                "shape":    "rect",
            },
        ],
    },

    "0845": {
        "label":          "3-Way Pen - 0845",
        "material":       "three_way_pen",
        "has_neoprene":    False,
        "has_stitching":   False,
        "proof_shape":     "flat",
        "proof_warp":      0,
        "page_w":          852.58,
        "page_h":          333.08,
        "template_zones": {
            "barrel_side1": {"x": 0.2826, "y": 0.3897, "w": 0.2745, "h": 0.0624, "l": "Barrel (RH)"},
            "clip_side1":   {"x": 0.5740, "y": 0.3897, "w": 0.1314, "h": 0.0624, "l": "Clip (RH)"},
            "clip_side2":   {"x": 0.2607, "y": 0.5769, "w": 0.1212, "h": 0.0624, "l": "Clip (LH)"},
            "barrel_side2": {"x": 0.4094, "y": 0.5769, "w": 0.2741, "h": 0.0624, "l": "Barrel (LH)"},
        },
        "proof_bounds": {
            "barrel_side1": {"x": 345, "y": 576, "w": 449, "h": 39},
            "clip_side1":   {"x": 822, "y": 576, "w": 215, "h": 39},
            "clip_side2":   {"x": 318, "y": 737, "w": 215, "h": 42},
            "barrel_side2": {"x": 691, "y": 737, "w": 448, "h": 42},
        },
        "color_components": ["barrel", "clip", "button"],
        "ink_black_only":   ["white", "mint", "soft lime", "peach fuzz", "bubblegum"],
        "art_slots": [
            {"id":"barrel_side1","label":"Barrel (RH)","size":"3.25\" W × 0.25\" H",
             "left_pt":240.93,"top_pt":-131.19,"w_pt":234.0,"h_pt":18.0,"rotation":0,"shape":"rect"},
            {"id":"clip_side1","label":"Clip (RH)","size":"1.57\" W × 0.25\" H",
             "left_pt":489.38,"top_pt":-131.19,"w_pt":112.0,"h_pt":18.0,"rotation":0,"shape":"rect"},
            {"id":"barrel_side2","label":"Barrel (LH)","size":"3.25\" W × 0.25\" H",
             "left_pt":222.25,"top_pt":-193.53,"w_pt":234.0,"h_pt":18.0,"rotation":180,"shape":"rect"},
            {"id":"clip_side2","label":"Clip (LH)","size":"1.57\" W × 0.25\" H",
             "left_pt":471.01,"top_pt":-193.53,"w_pt":112.0,"h_pt":18.0,"rotation":180,"shape":"rect"},
        ],
    },

    
    "0070-3w": {
        "label":        "Kolder Kaddy 4CP - 0070-3w",

  "bleed_placement": {
    "side1": {
      "ox": 262,
      "oy": 241,
      "sc": 0.99,
      "strx": 1.56,
      "stry": 1.42,
      "warp": 95
    },
    "side2": {
      "ox": 286,
      "oy": 256,
      "sc": 0.99,
      "strx": 1.59,
      "stry": 1.42,
      "warp": 95
    },
    "bottom": {
      "ox": 23,
      "oy": 61,
      "sc": 0.96,
      "strx": 1.26,
      "stry": 0.98,
      "warp": 0
    },
	  },
	  
  "proof_bounds": {
    "side1": {
      "x": 288,
      "y": 360,
      "w": 346,
      "h": 514
    },
    "bottom": {
      "x": 529,
      "y": 879,
      "w": 330,
      "h": 329
    },
    # side 2 and the bottom measured off the art-zone masks (as the 0070-3m):
    # side 2 was 738/360 wide, which sat the art 10 px left of the can's face.
    "side2": {
      "x": 756,
      "y": 354,
      "w": 346,
      "h": 515
	  },
	  },
  
        "template_ai":  "Master Symbol 0070.ai",
        "mockup_psd":   "Master_Mockup_0070.psd",
        "psb_layer":    "MASTER SYMBOL-0070",
        "material":     "neoprene_4cp",
        "has_neoprene":  False,
        "has_stitching": False,
        "is_4cp":        True,
        "proof_shape":   "cylinder",
        "proof_warp":    70,
        "page_w":        316.800,
        "page_h":        785.504,
        "template_zones": {
            "side1":  {"x": 0.1616, "y": 0.0684, "w": 0.6835, "h": 0.2767, "l": "Side 1"},
            "bottom": {"x": 0.2896, "y": 0.4149, "w": 0.4285, "h": 0.1729, "l": "Bottom"},
            "side2":  {"x": 0.1616, "y": 0.6572, "w": 0.6835, "h": 0.2767, "l": "Side 2"},
        },
        "bleed_zone_full": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        "bleed_zones": {
            "side1":  {"x": 0.1083, "y": 0.0194, "w": 0.7884, "h": 0.3747},
            "bottom": {"x": 0.2896, "y": 0.4149, "w": 0.4285, "h": 0.1729},
            "side2":  {"x": 0.1083, "y": 0.6086, "w": 0.7884, "h": 0.3747},
        },
        "art_slots": [
            {
                "id":       "side1",
                "label":    "Side 1",
                "size":     "3\" W × 3\" H",
                "left_pt":  51.20,
                "top_pt":   -53.74,
                "w_pt":     216.53,
                "h_pt":     217.36,
                "rotation": 0,
                "shape":    "rect",
            },
            {
                "id":       "bottom",
                "label":    "Bottom",
                "size":     "1.875\" diameter",
                "left_pt":  91.73,
                "top_pt":   -325.91,
                "w_pt":     135.73,
                "h_pt":     135.82,
                "rotation": 180,
                "shape":    "circle",
            },
            {
                "id":       "side2",
                "label":    "Side 2",
                "size":     "3\" W × 3\" H",
                "left_pt":  51.20,
                "top_pt":   -516.28,
                "w_pt":     216.53,
                "h_pt":     217.36,
                "rotation": 180,
                "shape":    "rect",
            },
        ],
    },

    "1080-3w": {
        "label":        "Kolder Kaddy Slim Can 4CP - 1080-3w",
  "bleed_placement": {
    "side1": {
      "ox": 82,
      "oy": 39,
      "sc": 0.8,
      "strx": 1.18,
      "stry": 0.98,
      "warp": 70
    },
    "side2": {
      "ox": 73,
      "oy": 211,
      "sc": 0.8,
      "strx": 1.16,
      "stry": 0.96,
      "warp": 70
    },
    "bottom": {
      "ox": 45,
      "oy": 125,
      "sc": 0.81,
      "strx": 0.74,
      "stry": 1,
      "warp": 0
    }
  },
  "proof_bounds": {
    "side1": {
      "x": 272,
      "y": 300,
      "w": 292,
      "h": 657
    },
    "side2": {
      "x": 768,
      "y": 294,
      "w": 292,
      "h": 643
    },
    "bottom": {
      "x": 527,
      "y": 946,
      "w": 260,
      "h": 260
    }
  },
        "template_ai":  "Master Symbol 1080-3m.ai",
        "mockup_psd":   "Master_Mockup_1080-3m.psd",
        "psb_layer":    "MASTER SYMBOL-1080-3m",
        "material":     "neoprene_4cp",
        "has_neoprene":  False,
        "has_stitching": False,
        "is_4cp":        True,
        "proof_shape":   "cylinder",
        "proof_warp":    70,
        "page_w":        321.3828,
        "page_h":        989.3225,
        "template_zones": {
            "side1":  {"x": 0.1593, "y": 0.0508, "w": 0.6768, "h": 0.3354, "l": "Side 1"},
            "bottom": {"x": 0.3068, "y": 0.4370, "w": 0.3817, "h": 0.1229, "l": "Bottom"},
            "side2":  {"x": 0.1593, "y": 0.6108, "w": 0.6768, "h": 0.3354, "l": "Side 2"},
        },
        "bleed_zone_full": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
  "bleed_zones": {
    "bottom": {
      "h": 0.149,
      "w": 0.476,
      "x": 0.246,
      "y": 0.424
    },
    "side1": {
      "h": 0.381,
      "w": 0.791,
      "x": 0.084,
      "y": 0.039
    },
    "side2": {
      "h": 0.3747,
      "w": 0.7884,
      "x": 0.1083,
      "y": 0.595
    },
  },
        "art_slots": [
            {
                "id":       "side1",
                "label":    "Side 1",
                "size":     "2.8\" W × 4.6\" H",
                "left_pt":  61.4232,
                "top_pt":   -50.2951,
                "w_pt":     201.6,
                "h_pt":     331.2,
                "rotation": 0,
                "shape":    "rect",
            },
            {
                "id":       "bottom",
                "label":    "Bottom",
                "size":     "1.7\" diameter",
                "left_pt":  101.025,
                "top_pt":   -431.4762,
                "w_pt":     122.4,
                "h_pt":     122.4,
                "rotation": 0,
                "shape":    "circle",
            },
            {
                "id":       "side2",
                "label":    "Side 2",
                "size":     "2.8\" W × 4.6\" H",
                "left_pt":  61.4256,
                "top_pt":   -603.8574,
                "w_pt":     201.6,
                "h_pt":     331.2,
                "rotation": 180,
                "shape":    "rect",
            },
        ],
    },


    "0837-3pk": {
        "label":        "Jotter 3-Pack - 0837-3pk",
        "template_ai":  "Master Symbol 0837-3pk.ai",
        "mockup_psd":   "Master_Mockup_0837-3pk.psd",
        "psb_layer":    "MASTER SYMBOL-0837-3pk",
        "material":     "jotter",
        "has_neoprene":  False,
        "has_stitching": False,
        "proof_shape":   "flat",
        "proof_warp":    0,
        "color_components": ["pen1","pen2","pen3","card_front","card_back"],
        "show_ink":      False,
        "proof_imprint_inset": {
            "pen1":       {"t": 0.0, "r": 0.0, "b": 0.0, "l": 0.0},
            "pen2":       {"t": 0.0, "r": 0.0, "b": 0.0, "l": 0.0},
            "pen3":       {"t": 0.0, "r": 0.0, "b": 0.0, "l": 0.0},
            "card_front": {"t": 0.0, "r": 0.0, "b": 0.0, "l": 0.0},
            "card_back":  {"t": 0.0, "r": 0.0, "b": 0.0, "l": 0.0},
        },
        "ink_black_only": ["gray", "white", "navy", "gold"],
        "page_w": 606.038,
        "page_h": 610.049,
        "template_zones": {
    "pen1": {"x": 0.2026, "y": 0.2780, "w": 0.0197, "h": 0.4226, "l": "Pen 1"},
    "pen2": {"x": 0.2622, "y": 0.2780, "w": 0.0197, "h": 0.4226, "l": "Pen 2"},
    "pen3": {"x": 0.3182, "y": 0.2780, "w": 0.0197, "h": 0.4226, "l": "Pen 3"},
    "card_front": {"x": 0.3965, "y": 0.1200, "w": 0.1873, "h": 0.7662, "l": "Front of Card"},
    "card_back": {"x": 0.6012, "y": 0.1200, "w": 0.1873, "h": 0.7662, "l": "Back of Card"}
},
        "proof_bounds": {
    "pen1": {
      "x": 377,
      "y": 404,
      "w": 37,
      "h": 610
    },
    "pen2": {
      "x": 467,
      "y": 404,
      "w": 37,
      "h": 610
    },
    "pen3": {
      "x": 560,
      "y": 404,
      "w": 37,
      "h": 610
    },
  "card_front": {
      "x": 280,
      "y": 149,
      "w": 399,
      "h": 1053
    },
    "card_back": {
      "x": 658,
      "y": 149,
      "w": 399,
      "h": 1053
    }
  },
        "bleed_zones": {},
        "art_slots": [
            {
                "id":       "pen1",
                "label":    "Pen 1",
                "size":     "0.25\" W × 4.25\" H",
                "left_pt":  16.7544,
                "top_pt":   -144.5832,
                "w_pt":     18.000,
                "h_pt":     306.000,
                "rotation": 270,
                "shape":    "rect",
            },
            {
                "id":       "pen2",
                "label":    "Pen 2",
                "size":     "0.25\" W × 4.25\" H",
                "left_pt":  74.0520,
                "top_pt":   -144.5832,
                "w_pt":     18.000,
                "h_pt":     306.000,
                "rotation": 270,
                "shape":    "rect",
            },
            {
                "id":       "pen3",
                "label":    "Pen 3",
                "size":     "0.25\" W × 4.25\" H",
                "left_pt":  127.9800,
                "top_pt":   -144.5832,
                "w_pt":     18.000,
                "h_pt":     306.000,
                "rotation": 270,
                "shape":    "rect",
            },
            {
                "id":       "card_front",
                "label":    "Front of Card",
                "size":     "2.25\" W × 7.5\" H",
                "left_pt":  211.7808,
                "top_pt":   -37.7928,
                "w_pt":     162.000,
                "h_pt":     540.000,
                "rotation": 0,
                "shape":    "rect",
            },
            {
                "id":       "card_back",
                "label":    "Back of Card",
                "size":     "2.25\" W × 7.5\" H",
                "left_pt":  409.8312,
                "top_pt":   -37.7928,
                "w_pt":     162.000,
                "h_pt":     540.000,
                "rotation": 0,
                "shape":    "rect",
            },
        ],
    },

    # ── Main Squeeze tote, natural canvas ────────────────────────────────────
    #
    # The first flat-goods item in the catalogue. Everything above is a koozie
    # or a pen; this is a bag, and the differences that matter are recorded
    # here rather than special-cased downstream.
    #
    # Natural is its own product because it is priced differently from the dyed
    # canvases — 5001-cc is a separate catalogue entry sharing these assets, not
    # a colour option on this one.
    #
    # page_w/page_h are the die laid flat, measured off the template's die
    # outline: 14.51" x 31.01". The imprint zone below was measured twice from
    # independent sources that agree to 1.6 pt — the cyan rectangle on the guide
    # page, and the magenta centre crosshairs on the press sheet.
    #
    # One imprint for now. The standard 5001-7 prints two sides, and adding it
    # needs an art_zone_side2 layer for the left-hand bag in the mockup, which
    # the asset set does not yet include.
    "5001-7": {
        "label":         "Main Squeeze Tote - 5001-7",
        "template_ai":   "5001-TIF-7-1C.ai",
        "mockup_psd":    "Master_Mockup 5001-7.psd",
        "psb_layer":     "MASTER SYMBOL-5001-7",
        "material":      "cotton_canvas",
        "has_neoprene":  False,
        "has_stitching": False,
        # Flat goods: the proof lays the panel out square rather than wrapping
        # it round a can, so there is no warp to apply.
        "proof_shape":   "flat",
        "proof_warp":    0,
        # Scaled from the purple outline against the finished item's stated
        # size (13.5" x 14"), not from the die. The die outline includes seam
        # allowance, so measuring from it put every derived figure about 1.7%
        # out. Anchoring to the purple instead makes the hem band land on
        # exactly 1.00", which is the check that the scale is right.
        "page_w":        1031.10,
        "page_h":        2205.50,
        # The tote prints to the edge of the panel, not to a box inside it.
        #
        # The template's two cyan rectangles are BOTH suggestions — sizes that
        # look right on the bag — and neither is a limit. The limit is the
        # purple outline, which is the tote's own shape, less the red hatched
        # band at the top: that is the hem, and anything printed there is
        # stitched over.
        #
        # So the printable area is the panel minus the hem, 13.5" x 13",
        # and the 8" x 10" inner rectangle is guidance the configurator can
        # show but must not enforce.
        "template_zones": {
            "side1": {"x": 0.0254, "y": 0.0772, "w": 0.9427, "h": 0.4244,
                      "l": "Side 1 (Front)"},
            "side2": {"x": 0.0254, "y": 0.4984, "w": 0.9427, "h": 0.4244,
                      "l": "Side 2 (Back)"},
        },
        # The size most marks should be drawn at. Not a constraint — shown to
        # the customer so a full-panel print is a deliberate choice rather than
        # an accident.
        "suggested_imprint": '8" W × 10" H',
        "art_slots": [
            {
                "id":       "side1",
                "label":    "Side 1 (Front)",
                "size":     '13.5" W × 13" H',
                "left_pt":  26.19,
                "top_pt":   -170.33,
                "w_pt":     972.00,
                "h_pt":     936.00,
                "rotation": 0,
                "shape":    "rect",
            },
            # The back panel, mirrored about the die's fold line — its hem is
            # at the bottom of the flat die, since the two panels share one
            # opening. Printed head-down like the koozies' Side 2.
            {
                "id":       "side2",
                "label":    "Side 2 (Back)",
                "size":     '13.5" W × 13" H',
                "left_pt":  26.19,
                "top_pt":   -1099.13,
                "w_pt":     972.00,
                "h_pt":     936.00,
                "rotation": 180,
                "shape":    "rect",
            },
        ],
    },

}

# ─────────────────────────────────────────────────────────────────────────────
# This Is Fast — one-color screen print program
# ─────────────────────────────────────────────────────────────────────────────
#
# This Is Fast items are SEPARATE products that sit alongside the originals.
# Nothing above this line changes: 0070-3m keeps working exactly as it always
# has, and a twin called 0070-3m-24HR-1c is generated beside it carrying the
# one-color screen-print workflow (vector-only uploads, PMS ink, the onboarding
# tutorial, the spot-color export).
#
# The twin reuses the base product's mockup and template assets through
# "asset_id", so no artwork has to be duplicated on disk.
#
# To add another This Is Fast item: put its base product id in
# SCREENPRINT_BASE_IDS. The twin, its SKU, the API, the configurator UI and the
# upload validation all follow from that one entry.

import copy

# ── Main Squeeze tote, colour canvas ─────────────────────────────────────────
#
# The same bag as 5001-7: same die, same imprint area, same mockup artwork.
# The only difference is that the canvas is dyed, which is a different price
# and therefore a different item number.
#
# Derived from 5001-7 rather than written out again, so a correction to the
# imprint geometry can never land on one and miss the other. It keeps
# asset_id "5001-7" so both share one set of mockup layers on disk.
PRODUCTS["5001-cc"] = copy.deepcopy(PRODUCTS["5001-7"])
PRODUCTS["5001-cc"].update({
    "label":    "Main Squeeze Tote - 5001-cc",
    "material": "cotton_canvas_dyed",
    "asset_id": "5001-7",
})

# ── Daily Grind tote: 5010-10 natural, 5010-cc colour canvas ────────────────
#
# A gusseted canvas tote (12" W face, 4" bottom). One die, laid flat 17" x 34":
# Front half on top, Back half below, a 1.26" hem at each end that folds
# inside, the bottom between them. Imprint 11.03" x 11.5" (793.8 x 828 pt),
# centred on each face, as drawn by the cyan boxes on Numo's 1-up
# (press/tif/5010-1up.pdf) and the TIF template.
#
# Template space = the die on the TIF template (press/5010-TIF-1C.pdf page 1,
# die [573.5, 74.4, 1797.5, 2522.3] pt): 1224 x 2447.9 pt, top-down.
# Mockup: Numo's photo layers in static/assets/5010-10 (tools/
# make_5010_assets.py), right bag = Side 1 (Front), left = Side 2 (Back);
# proof_bounds: the cyan boxes on Numo's placement image of that mockup.
# The full item prints both sides; the This Is Fast twins print the Front
# (SCREENPRINT_SLOT_LIMITS).
_DG_W, _DG_H = 1224.0, 2447.9
PRODUCTS["5010-10"] = {
    "label":         "Daily Grind Tote - 5010-10",
    "material":      "cotton_canvas",
    "asset_id":      "5010-10",
    "has_neoprene":  False,
    "has_stitching": False,
    "proof_shape":   "flat",
    "proof_warp":    0,
    "page_w":        _DG_W,
    "page_h":        _DG_H,
    "template_zones": {
        "side1": {"x": round(216.5 / _DG_W, 4), "y": round(205.5 / _DG_H, 4),
                  "w": round(793.8 / _DG_W, 4), "h": round(828.0 / _DG_H, 4), "l": "Side 1 (Front)"},
        "side2": {"x": round(216.5 / _DG_W, 4), "y": round(1412.6 / _DG_H, 4),
                  "w": round(793.8 / _DG_W, 4), "h": round(828.0 / _DG_H, 4), "l": "Side 2 (Back)"},
    },
    # On the 1350 px mockup canvas: Numo's placement image (2400 px) cyan
    # boxes x 1381 / 314, y 1578 / 897, 710 x 741, scaled by 1350/2400.
    "proof_bounds": {
        "side1": {"x": 777, "y": 888, "w": 399, "h": 417},
        "side2": {"x": 177, "y": 505, "w": 399, "h": 417},
    },
    "bleed_zones": {},
    "art_slots": [
        {"id": "side1", "label": "Side 1 (Front)", "size": '11.03" W × 11.5" H',
         "left_pt": 216.5, "top_pt": -205.5, "w_pt": 793.8, "h_pt": 828.0,
         "rotation": 0, "shape": "rect"},
        # The Back half of the die, head-down on the flat die (it shares the
        # bag's opening with the Front), like the Main Squeeze's Side 2.
        {"id": "side2", "label": "Side 2 (Back)", "size": '11.03" W × 11.5" H',
         "left_pt": 216.5, "top_pt": -1412.6, "w_pt": 793.8, "h_pt": 828.0,
         "rotation": 180, "shape": "rect"},
    ],
}
PRODUCTS["5010-cc"] = copy.deepcopy(PRODUCTS["5010-10"])
PRODUCTS["5010-cc"].update({
    "label":    "Daily Grind Tote - 5010-cc",
    "material": "cotton_canvas_dyed",
    "asset_id": "5010-10",
})

# ── Shamwow tote: 5020-10 natural, 5020-cc colour canvas ────────────────────
#
# A bigger tote with a boxed bottom. One die laid flat 17" x 37.5": Front
# half on top, Back half below, a hem at each end, the bottom between.
# Imprint 15" x 13" (1080 x 936 pt) on each face, its two lower corners cut
# off (2.06" x 3") where the bottom folds - the zone is the 15" x 13" box,
# so keep art clear of those corners. From Numo's 1-up
# (press/tif/5020-1up.pdf) and the TIF template.
#
# Template space = the die on the TIF template (press/5020-TIF-1C.pdf page 1,
# die [1069.1, 191.2, 2293.2, 2891.5] pt): 1224.1 x 2700.3 pt, top-down.
# Mockup: Numo's photo layers in static/assets/5020-10 (tools/
# make_5020_assets.py), right bag = Side 1 (Front), left = Side 2 (Back);
# proof_bounds: the cyan boxes on Numo's placement image (2400 px: x 1313.5 /
# 134.5, y 1335 / 873, 930 x 818.5), scaled by 1350/2400.
# The full item prints both sides; the This Is Fast twins print the Front.
_SW_W, _SW_H = 1224.1, 2700.3
PRODUCTS["5020-10"] = {
    "label":         "Shamwow Tote - 5020-10",
    "material":      "cotton_canvas",
    "asset_id":      "5020-10",
    "has_neoprene":  False,
    "has_stitching": False,
    "proof_shape":   "flat",
    "proof_warp":    0,
    "page_w":        _SW_W,
    "page_h":        _SW_H,
    "template_zones": {
        "side1": {"x": round(72.0 / _SW_W, 4), "y": round(197.6 / _SW_H, 4),
                  "w": round(1080.0 / _SW_W, 4), "h": round(936.0 / _SW_H, 4), "l": "Side 1 (Front)"},
        "side2": {"x": round(72.0 / _SW_W, 4), "y": round(1566.65 / _SW_H, 4),
                  "w": round(1080.0 / _SW_W, 4), "h": round(936.0 / _SW_H, 4), "l": "Side 2 (Back)"},
    },
    "proof_bounds": {
        "side1": {"x": 739, "y": 751, "w": 523, "h": 460},
        "side2": {"x": 76,  "y": 491, "w": 523, "h": 460},
    },
    "bleed_zones": {},
    "art_slots": [
        {"id": "side1", "label": "Side 1 (Front)", "size": '15" W × 13" H',
         "left_pt": 72.0, "top_pt": -197.6, "w_pt": 1080.0, "h_pt": 936.0,
         "rotation": 0, "shape": "rect"},
        {"id": "side2", "label": "Side 2 (Back)", "size": '15" W × 13" H',
         "left_pt": 72.0, "top_pt": -1566.65, "w_pt": 1080.0, "h_pt": 936.0,
         "rotation": 180, "shape": "rect"},
    ],
}
PRODUCTS["5020-cc"] = copy.deepcopy(PRODUCTS["5020-10"])
PRODUCTS["5020-cc"].update({
    "label":    "Shamwow Tote - 5020-cc",
    "material": "cotton_canvas_dyed",
    "asset_id": "5020-10",
})

# ── Metallic neoprene: 0070-3l and 1080-3l ──────────────────────────────────
#
# The same can coolers as 0070-3m and 1080-3m — same die, same imprint areas,
# same mockup and press templates — in metallic neoprene (Gold, Rose Gold,
# Silver), printed in at most THREE PMS inks instead of five. Derived from
# the 3m rather than written out again, so a geometry correction can never
# land on one and miss the other.
#
# NetSuite doesn't tell them apart by item: a 3l line comes in as the 3m
# item with a metallic body colour. Any neoprene line whose body is one of
# METALLIC_BODY_COLORS is treated as the 3l (configurator side, on opening a
# line or an order).
#
# The bodies are printed materials, like the camo on scuba: images in
# static/assets/<3l id>/patterns/ (patterns.json: name, hex, swatch, body,
# tile — make them with tools/make_body_pattern.py). The 3l offers those and
# no solid colours.
METALLIC_TWINS = {"0070-3m": "0070-3l", "1080-3m": "1080-3l"}
METALLIC_BODY_COLORS = ["Gold", "Rose Gold", "Silver"]
METALLIC_MAX_INKS = 3


def metallic_body(name):
    """The metallic body a NetSuite / configurator colour name means, or None:
    "GOLD", "Metallic Gold", "Rose Gold Metallic", "silver" ..."""
    import re as _re
    t = _re.sub(r"[^a-z ]+", " ", str(name or "").lower())
    if _re.search(r"\brose\s*gold\b", t):
        return "Rose Gold"
    if _re.search(r"\bgold\b", t):
        return "Gold"
    if _re.search(r"\bsilver\b", t):
        return "Silver"
    return None


for _bid, _mid in METALLIC_TWINS.items():
    _b = PRODUCTS.get(_bid)
    if not _b:
        continue
    _m = copy.deepcopy(_b)
    _m.update({
        "label":          (_b.get("label") or _bid).replace(_bid, _mid),
        "material":       "neoprene_metallic",
        "asset_id":       _b.get("asset_id") or _bid,     # mockup layers: the 3m's
        "pattern_dir":    _mid,                            # its bodies: its own
        "metal_of":       _bid,
        "max_spot_inks":  METALLIC_MAX_INKS,
    })
    PRODUCTS[_mid] = _m


# ── Heathered neoprene: 0070-3h and 1080-3h ─────────────────────────────────
#
# Same idea as the metallic 3l: the 3m can coolers in heathered jersey-knit
# neoprene (Athletic Gray, Charcoal), each its own item (0070-3H-1C ...).
# Same die, templates and mockup layers as the 3m; the bodies are printed
# images in static/assets/<3h id>/patterns/. Ink limit: the 3m's (5).
# A NetSuite 3m line with a heathered body colour opens as the 3h.
HEATHERED_TWINS = {"0070-3m": "0070-3h", "1080-3m": "1080-3h"}
HEATHERED_BODY_COLORS = ["Athletic Gray", "Charcoal"]


def heathered_body(name):
    """The heathered body a NetSuite / configurator colour name means, or None:
    "Heathered Charcoal (Dark)", "Athletic Gray", "Heather Grey" ... A plain
    "Gray" is the 3m's solid gray, not a heather."""
    import re as _re
    t = _re.sub(r"[^a-z ]+", " ", str(name or "").lower())
    if _re.search(r"\bcharcoal\b", t):
        return "Charcoal"
    if _re.search(r"\bathletic\b", t) or _re.search(r"\bheather(ed)?\s+gr[ae]y\b", t):
        return "Athletic Gray"
    return None


for _bid, _hid in HEATHERED_TWINS.items():
    _b = PRODUCTS.get(_bid)
    if not _b:
        continue
    _h = copy.deepcopy(_b)
    _h.update({
        "label":          (_b.get("label") or _bid).replace(_bid, _hid),
        "material":       "neoprene_heathered",
        "asset_id":       _b.get("asset_id") or _bid,
        "pattern_dir":    _hid,
        "twin_of":        _bid,
        "twin_kind":      "heathered",
    })
    PRODUCTS[_hid] = _h

for _bid, _mid in METALLIC_TWINS.items():
    if _mid in PRODUCTS:
        PRODUCTS[_mid].update({"twin_of": _bid, "twin_kind": "metallic"})


# ── Own-cut neoprene: denim (-3u), burlap (-3b), suede (-3s) ───────────────────────────────────────
#
# Denim (and later burlap, suede) doesn't stretch like neoprene, so it is cut
# bigger before sewing and has its OWN press template and sheet positions
# (press/<id>-24HR-1c.pdf + press_spec_<id>.json, built with
# tools/make_press_template.py from the Mass Export). Everything the customer
# sees is the 3m's: same mockup, same maximum imprint (3" x 3" sides, 1.875"
# bottom), same stitching. The body is a printed image (patterns/).
#
# NetSuite: the item is 0070-3U-#C. A line for it — or a 3m line with a denim
# body — opens here.
OWN_CUT_ITEMS = {
    # id         base        kind      material             item prefix
    "0070-3u": ("0070-3m", "denim", "neoprene_denim", "0070-3U"),
    "0070-3b": ("0070-3m", "burlap", "neoprene_burlap", "0070-3B"),
    "1080-3u": ("1080-3m", "denim", "neoprene_denim", "1080-3U"),
    "1080-3b": ("1080-3m", "burlap", "neoprene_burlap", "1080-3B"),
    "0070-3s": ("0070-3m", "suede", "neoprene_suede", "0070-3S"),
    "1080-3s": ("1080-3m", "suede", "neoprene_suede", "1080-3S"),
    # MMKK: the Kolder Kaddy with a magnet sewn on one side. Same cut and
    # silhouette as 0070-3m and the same neoprene colors; its own press sheets
    # ("0262 - Neo - Mass Export") and item number.
    "0262-3m": ("0070-3m", "magnet", "neoprene", "0262"),
}
OWN_CUT_BODY = {"denim": ["Denim"], "burlap": ["Burlap"], "suede": ["Smoke"]}


def own_cut_body(name):
    """The own-cut body a colour name means ("Denim", "Blue Denim" ...) as (kind, body), or None."""
    import re as _re
    t = _re.sub(r"[^a-z ]+", " ", str(name or "").lower())
    if _re.search(r"\bdenim\b", t):
        return "denim", "Denim"
    if _re.search(r"\b(burlap|jute)\b", t):
        return "burlap", "Burlap"
    if _re.search(r"\b(suede|smoke)\b", t):
        return "suede", "Smoke"
    return None


OWN_CUT_LABELS = {"0262-3m": "Magnetic Kolder Kaddy - 0262-3m"}
OWN_CUT_ASSETS = {"0262-3m": "0262-3m"}

for _id, (_bid, _kind, _mat, _item) in OWN_CUT_ITEMS.items():
    _b = PRODUCTS.get(_bid)
    if not _b:
        continue
    _o = copy.deepcopy(_b)
    _o.update({
        "label":          (_b.get("label") or _bid).replace(_bid, _id),
        "material":       _mat,
        "asset_id":       _b.get("asset_id") or _bid,     # mockup: the 3m's
        "pattern_dir":    _id,                             # body: its own
        "twin_of":        _bid,
        "twin_kind":      _kind,
        "item_prefix":    _item,
        "own_cut":        True,
    })
    if _id in OWN_CUT_LABELS:
        _o["label"] = _o["display_label"] = OWN_CUT_LABELS[_id]
    if _id in OWN_CUT_ASSETS:                  # its own mockup layers (the magnet)
        _o["asset_id"] = OWN_CUT_ASSETS[_id]
    PRODUCTS[_id] = _o

# MMKK screen prints on Side 1 (and the bottom) only: Side 2 carries the magnet.
if "0262-3m" in PRODUCTS:
    PRODUCTS["0262-3m"]["art_slots"] = [s for s in PRODUCTS["0262-3m"]["art_slots"] if s.get("id") != "side2"]

# Things sewn on after printing, drawn on the proof's flat panels and the 2X2:
# the MMKK's magnet, centered on Side 2, about 1" x 3" (measured off the mockup
# photo — correct w_in / h_in here if the real magnet differs).
MMKK_MAGNET = {"slot": "side2", "file": "static/assets/0262-3m/magnet_flat.png",
               "w_in": 1.0, "h_in": 3.0, "dx_in": 0.0, "dy_in": 0.0}
if "0262-3m" in PRODUCTS:
    PRODUCTS["0262-3m"]["sewn_on"] = [dict(MMKK_MAGNET)]

# Burlap is an open weave: thin lines and small lettering fall into the holes
# between the threads, and ink wicks along them. Art on it is measured at its
# printed size against these (points), vector as well as raster — see porous.py.
# Tune to what the floor sees: line_pt is "prints solid", line_floor_pt is
# "likely to break up", gap_pt is the tightest gap that stays open.
BURLAP_LIMITS = {
    "name": "Burlap",
    "line_pt": 4.0,          # 0.056"
    "line_floor_pt": 2.5,    # 0.035"
    "gap_pt": 3.0,           # 0.042"
    "pattern_ppi": 90,       # the burlap body/tile photo, px per inch
}
for _id in ("0070-3b", "1080-3b"):
    if _id in PRODUCTS:
        PRODUCTS[_id]["porous"] = dict(BURLAP_LIMITS)

# Suede (Smoke) has a rough nap rather than holes: fine detail distorts a
# little, less than on burlap, so the limits are lower and the preview's
# texture through the ink is softer.
SUEDE_LIMITS = {
    "name": "Suede",
    "kind": "nap",
    "line_pt": 2.5,          # 0.035"
    "line_floor_pt": 1.5,    # 0.021"
    "gap_pt": 2.0,           # 0.028"
    "pattern_ppi": 90,
    "texture_strength": 0.45,
}
for _id in ("0070-3s", "1080-3s"):
    if _id in PRODUCTS:
        PRODUCTS[_id]["porous"] = dict(SUEDE_LIMITS)

SCREENPRINT_SKU_SUFFIX = "-24HR-1c"

SCREENPRINT_BASE_IDS = [
    "0070-3m",   # Kolder Kaddy
    "1080-3m",   # Kolder Kaddy Slim Can
    "0472",      # Kolder Kaddy Slim Can
    "9100",      # Pocket Coolie
    "5001-7",    # Main Squeeze tote, natural canvas — first flat-goods item
    "5001-cc",   # Main Squeeze tote, colour canvas
    "5010-10",   # Daily Grind tote, natural canvas
    "5010-cc",   # Daily Grind tote, colour canvas
    "5020-10",   # Shamwow tote, natural canvas
    "5020-cc",   # Shamwow tote, colour canvas
]

# Vector formats accepted for one-color screen-print artwork.
SCREENPRINT_VECTOR_EXTS = {".svg", ".pdf", ".ai", ".eps"}


# Geometry corrections that apply ONLY to the This Is Fast twins. The original
# products keep the exact slot positions they ship with today.
#
# 0070-3m/bottom: on the original the bottom slot sits 26.42 pt right of Side 1
# and Side 2, with 89.80 pt of space above it and 34.73 pt below. The twin
# centres it on the sides' axis with equal 62.27 pt gaps.
SCREENPRINT_SLOT_OVERRIDES = {
    "0070-3m": {
        "bottom": {"left_pt": 88.49, "top_pt": -329.01},
    },
}

# Imprint locations the This Is Fast twin prints, where it prints fewer than
# the original.
#
# The tote is the first item where the two differ: the standard 5001-7 prints
# front and back, but the 24-hour one-color version prints the front only, and
# its press template is imposed accordingly. A twin absent from here keeps
# every slot its base product has, which is what all four koozies do.
SCREENPRINT_SLOT_LIMITS = {
    "5001-7":  ["side1"],
    "5001-cc": ["side1"],
    "5010-10": ["side1"],
    "5010-cc": ["side1"],
    "5020-10": ["side1"],
    "5020-cc": ["side1"],
}


# Item numbers for twins that do not follow the "<base>-24HR-1c" pattern.
#
# The koozies are named by suffixing the base: 0070-3m -> 0070-3m-24HR-1c. The
# totes are not — their This Is Fast numbers put the programme in the middle,
# 5001-7 -> 5001-TIF-7-1C. The item number is what the press room and the order
# system use, so it has to be the real one rather than one this file invents.
SCREENPRINT_TWIN_IDS = {
    "5001-7":  "5001-TIF-7-1C",
    "5001-cc": "5001-TIF-CC-1C",
    "5010-10": "5010-TIF-10-1C",
    "5010-cc": "5010-TIF-CC-1C",
    "5020-10": "5020-TIF-10-1C",
    "5020-cc": "5020-TIF-CC-1C",
}


def _variant_id(base_id):
    override = SCREENPRINT_TWIN_IDS.get(base_id)
    if override:
        return override
    return f"{base_id}{SCREENPRINT_SKU_SUFFIX}"


def _variant_label(base_id, base_label):
    """'Kolder Kaddy - 0070-3m' -> 'Kolder Kaddy - 0070-3m-24HR-1c'."""
    vid = _variant_id(base_id)
    # Labels end in the item number, so swapping the base number for the twin's
    # keeps the name readable whichever naming pattern the twin follows.
    if base_label and base_label.endswith(base_id):
        return f"{base_label[:-len(base_id)]}{vid}"
    return f"{base_label or base_id} ({vid})"


# Build the twins. Deep-copied so edits to one never leak into the other.
for _bid in SCREENPRINT_BASE_IDS:
    _base = PRODUCTS.get(_bid)
    if not _base:
        continue
    _v = copy.deepcopy(_base)
    # Reuse the base product's assets. Where the base itself borrows another
    # product's artwork — 5001-cc is the same bag as 5001-7, only dyed — the
    # twin has to follow that borrowing rather than point at a folder named
    # after itself, which would not exist.
    _v["asset_id"]       = _base.get("asset_id") or _bid
    _v["base_id"]        = _bid
    _v["is_screenprint"] = True
    _v["label"]          = _variant_label(_bid, _base.get("label") or _bid)
    _keep = SCREENPRINT_SLOT_LIMITS.get(_bid)
    if _keep:
        _v["art_slots"] = [s for s in _v.get("art_slots", []) if s["id"] in _keep]
        _v["template_zones"] = {k: z for k, z in (_v.get("template_zones") or {}).items()
                                if k in _keep}
        if _v.get("proof_bounds"):
            _v["proof_bounds"] = {k: b for k, b in _v["proof_bounds"].items() if k in _keep}
    for _slot in _v.get("art_slots", []):
        _fix = (SCREENPRINT_SLOT_OVERRIDES.get(_bid) or {}).get(_slot["id"])
        if _fix:
            _slot.update(_fix)
    PRODUCTS[_variant_id(_bid)] = _v

SCREENPRINT_PRODUCT_IDS = {_variant_id(b) for b in SCREENPRINT_BASE_IDS
                           if _variant_id(b) in PRODUCTS}


# ── This Is Fast Jotter: 0837-24HR-IMP ─────────────────────────────────────
#
# The 0837 Jotter in the 24-hour programme: the same pen, printed the same way
# (multi-color digital, Mimaki, the jig's 4.28" x 0.25" box, up to two sides),
# under its own item number. Not one of the one-color screen-print twins above,
# so it is derived here rather than through SCREENPRINT_BASE_IDS. It keeps
# asset_id "0837" (one set of mockup layers) and the 0837's Mimaki jig.
# The customer's filled-in template is read by tif_import (EXTRA_TEMPLATES).
PRODUCTS["0837-24HR-IMP"] = copy.deepcopy(PRODUCTS["0837"])
PRODUCTS["0837-24HR-IMP"].update({
    "label":          "Jotter Retractable Pen - 0837-24HR-IMP",
    "asset_id":       "0837",
    "base_id":        "0837",
    "program":        "This Is Fast",
    "printing_label": "Full color · digital",
})


# ── multi-color spot assignment ─────────────────────────────────────────────
# Products whose uploaded artwork is separated into spot inks, each of which
# the customer assigns a PMS color to. Opt-in by product id, the same way
# SCREENPRINT_BASE_IDS works, so nothing else in the catalog changes behavior.
#
# These are ORIGINALS, not twins. The This Is Fast twins print one color and
# must never appear here — is_screenprint() and supports_pms_assign() are
# mutually exclusive by construction, and the guard below enforces that rather
# than trusting the list to stay correct.
#
# To offer this on another product: add its id. It needs no press template —
# assignment drives the preview and the proof, not the press sheets.
PMS_ASSIGN_PRODUCT_IDS = [
    "0070-3m",   # Kolder Kaddy
    "1080-3m",   # Kolder Kaddy Slim Can
    "0070-3l",   # Kolder Kaddy, metallic (3 inks)
    "1080-3l",   # Kolder Kaddy Slim Can, metallic (3 inks)
    "0070-3h",   # Kolder Kaddy, heathered
    "1080-3h",   # Kolder Kaddy Slim Can, heathered
    "0070-3u",   # Kolder Kaddy, denim (own cut)
    "0070-3b",   # Kolder Kaddy, burlap (own cut)
    "1080-3u",   # Kolder Kaddy Slim Can, denim (own cut)
    "1080-3b",   # Kolder Kaddy Slim Can, burlap (own cut)
    "0070-3s",   # Kolder Kaddy, suede (own cut)
    "1080-3s",   # Kolder Kaddy Slim Can, suede (own cut)
    "0262-3m",   # Magnetic Kolder Kaddy (MMKK)
    "0472",      # Kolder Kaddy Slim Can, 12 oz
    "9100",      # Pocket Coolie
]


def supports_pms_assign(product_id):
    """True for originals that separate artwork into assignable spot inks."""
    if product_id not in PMS_ASSIGN_PRODUCT_IDS:
        return False
    # A twin slipping into the list would put a 4-color picker on a 1-color
    # product. Refuse rather than offer it.
    return not bool((PRODUCTS.get(product_id) or {}).get("is_screenprint"))


def is_screenprint(product_id):
    """True only for the This Is Fast twins, never for the originals."""
    return bool((PRODUCTS.get(product_id) or {}).get("is_screenprint"))


def screenprint_sku(product_id):
    """The identifier shown, stored and submitted. Twins already carry the suffix."""
    return product_id


def display_label(product_id, label=None):
    """The product name as shown to the customer."""
    if label is None:
        label = (PRODUCTS.get(product_id) or {}).get("label") or product_id
    return label


def asset_id_for(product_id):
    """Which folder under /static/assets holds this product's artwork."""
    return (PRODUCTS.get(product_id) or {}).get("asset_id") or product_id


# Normalise the flags across every product so callers can read them directly.
for _pid, _p in PRODUCTS.items():
    _p.setdefault("is_screenprint", False)
    _p.setdefault("asset_id", _pid)
    _p["sku"] = screenprint_sku(_pid)
    _p["display_label"] = display_label(_pid, _p.get("label") or _pid)
    _p["supports_pms_assign"] = supports_pms_assign(_pid)

for _n in ("_bid", "_base", "_v", "_pid", "_p", "_slot", "_fix"):
    globals().pop(_n, None)


# ─────────────────────────────────────────────────────────────────────────────
# 4CP print geometry, measured from Numo's Fiery templates (press/fiery/*.pdf)
# ─────────────────────────────────────────────────────────────────────────────
# The 4CP production file is printed on the Fiery at exactly the template's
# size, with the template's notches, so page size and every imprint position
# come from those files. The 1080's older numbers were on a page 22 pt too wide,
# which put the design 0.17" right of centre; the others were within 0.05".
# Positions measured from the Fiery templates' guides (Illustrator). Every
# location on these templates is upright except the second side, which reads
# upside down; on the 0472 the upright top panel is the Front (Side 1).
# Slot value: (left, top) or (left, top, w, h, rotation).
FIERY_4CP = {
    "0070-3w": {"page": (316.373, 785.07), "template": "press/fiery/0070-3w.pdf",
               "slots": {"side1": (49.921, -52.94), "bottom": (90.322, -325.11, None, None, 0),
                         "side2": (49.921, -515.48)}},
    "1080-3w": {"page": (299.534, 988.462), "template": "press/fiery/1080-3w.pdf",
               "slots": {"side1": (48.967, -52.4), "bottom": (88.567, -433.1), "side2": (48.967, -604.6)}},
    "0472-4CP": {"page": (319.383, 999.818), "template": "press/fiery/0472-4CP.pdf",
               "slots": {"side1": (51.691, -55.473, None, None, 0),
                         "bottom": (105.69, -445.77, 108.0, 108.0, 0),
                         "side2": (51.691, -619.66, None, None, 180)}},
    "9100-4CP": {"page": (346.623, 827.86), "template": "press/fiery/9100-4CP.pdf",
               "slots": {"side1": (47.311, -48.41), "bottom": (114.811, -355.39, None, None, 0),
                         "side2": (47.311, -525.77)}},
}
for _pid, _f in FIERY_4CP.items():
    _p = PRODUCTS.get(_pid)
    if not _p:
        continue
    _p["page_w"], _p["page_h"] = _f["page"]
    _p["fiery_template"] = _f["template"]
    for _s in _p.get("art_slots", []):
        _v = _f["slots"].get(_s["id"])
        if not _v:
            continue
        _s["left_pt"], _s["top_pt"] = _v[0], _v[1]
        if len(_v) > 2:
            if _v[2] is not None:
                _s["w_pt"], _s["h_pt"] = _v[2], _v[3]
                _s["size"] = f'{_v[2] / 72:.2f}" diameter' if _s.get("shape") == "circle" else _s.get("size")
            _s["rotation"] = _v[4]


def max_spot_inks(product_id, default=5):
    """The most PMS inks (screens) a product prints: its own limit (the
    metallic 3l: 3) or the press's (5)."""
    return int((PRODUCTS.get(product_id) or {}).get("max_spot_inks") or default)


# ── MMKK 4CP (0262-3w) ─────────────────────────────────────────────────────
# The full-colour koozies are still sewn, in a thread the customer picks like
# on the spot-colour ones (their mockups carry a stitching mask). Set before the
# 0262-3w copies the 0070-3w below.
for _pid in ("0070-3w", "1080-3w"):
    if _pid in PRODUCTS:
        PRODUCTS[_pid]["has_stitching"] = True

# The full-color Kolder Kaddy (0070-3w) with the magnet: printed full bleed on
# both sides like the 0070-3w, then the magnet is sewn on, so Side 2's art is
# hidden under it. Same Fiery template and geometry as the 0070-3w; its own
# mockup layers (static/assets/0262-3w) for the magnet.
if "0070-3w" in PRODUCTS:
    _w = copy.deepcopy(PRODUCTS["0070-3w"])
    _w.update({"label": "Magnetic Kolder Kaddy 4CP - 0262-3w",
               "display_label": "Magnetic Kolder Kaddy 4CP - 0262-3w",
               "asset_id": "0262-3w", "sku": "0262-3w",
               "twin_of": "0070-3w", "twin_kind": "magnet", "item_prefix": "0262-3W"})
    _w["sewn_on"] = [dict(MMKK_MAGNET, file="static/assets/0262-3w/magnet_flat.png")]
    PRODUCTS["0262-3w"] = _w


# ── Key Fob (0635-3m) ───────────────────────────────────────────────────────
# A neoprene strip folded over its middle and stitched at the ends: Side 1 is
# the left half of the flat strip, Side 2 the right, both printed upright.
# Spot-color screen print (standard item, up to 5 PMS). Template space is the
# 1-up (0635-3m-1up_screen_print, 587.8 x 72.5 pt); press sheets and proof
# geometry come from press/press_spec_0635-3m.json (tools/make_strip_template.py).
_FOB_W, _FOB_H = 587.827, 72.5
_FOB_ZONES = {"side1": (49.42, 9.438, 216.0, 54.0), "side2": (321.573, 9.438, 216.0, 54.0)}
PRODUCTS["0635-3m"] = {
    "label": "Key Fob - 0635-3m",
    "display_label": "Key Fob - 0635-3m",
    "material": "neoprene",
    "has_neoprene": True,
    "has_stitching": True,
    "proof_shape": "flat",
    "proof_warp": 0,
    "page_w": _FOB_W,
    "page_h": _FOB_H,
    "template_zones": {sid: {"x": round(x / _FOB_W, 4), "y": round((_FOB_H - y - h) / _FOB_H, 4),
                             "w": round(w / _FOB_W, 4), "h": round(h / _FOB_H, 4),
                             "l": "Side 1" if sid == "side1" else "Side 2"}
                       for sid, (x, y, w, h) in _FOB_ZONES.items()},
    "art_slots": [{"id": sid, "label": "Side 1" if sid == "side1" else "Side 2",
                   "size": '3" W × 0.75" H', "left_pt": x, "top_pt": -round(_FOB_H - y - h, 3),
                   "w_pt": w, "h_pt": h, "rotation": 0, "shape": "rect"}
                  for sid, (x, y, w, h) in _FOB_ZONES.items()],
    "asset_id": "0635-3m",
    "sku": "0635-3m",
    "item_prefix": "0635",
}
PRODUCTS["0635-3m"]["bleed_zones"] = {k: dict(v) for k, v in PRODUCTS["0635-3m"]["template_zones"].items()}
if "0635-3m" not in PMS_ASSIGN_PRODUCT_IDS:
    PMS_ASSIGN_PRODUCT_IDS.append("0635-3m")


# ── Neoprene construction (face / foam / back) ─────────────────────────────
# Most neoprene is the colour fabric over a black foam core with a black back
# fabric. Some colours have a white foam core, and the boxed pairs on the 3mm
# chart are two-sided: the back fabric is the other colour of the pair. The
# list lives in data/neoprene_construction.json so it can be edited without
# code. A product uses it only when it shows the inside or the cut edge:
#     "shows_inside": True   (off unless set; e.g. the 0070-3m later)
_NEO_BUILD = None


def _neo_build():
    global _NEO_BUILD
    if _NEO_BUILD is None:
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parent / "data" / "neoprene_construction.json"
        try:
            _NEO_BUILD = json.loads(p.read_text())
        except Exception:
            _NEO_BUILD = {"default": {"foam": "black", "back": "Black"}, "colors": {}}
        alias = {}
        for name, row in _NEO_BUILD.get("colors", {}).items():
            for a in row.get("aka", []):
                alias[a.lower()] = name
        _NEO_BUILD["_alias"] = alias
    return _NEO_BUILD


def neoprene_construction(color):
    """{"face", "foam", "back", "two_sided"} for a neoprene colour name."""
    b = _neo_build()
    name = (color or "").strip()
    rows = b.get("colors", {})
    key = next((k for k in rows if k.lower() == name.lower()), None) \
        or b["_alias"].get(name.lower())
    row = dict(b.get("default", {}), **(rows.get(key) or {}))
    back = row.get("back", "Black")
    return {"face": key or name, "foam": row.get("foam", "black"), "back": back,
            "two_sided": back.lower() not in ("black", (key or name).lower())}


def shows_inside(product_id):
    """Whether this product's mockup/proof should draw the foam and back."""
    return bool((PRODUCTS.get(product_id) or {}).get("shows_inside"))


# ── Key Fob mockup: the art bends onto each visible face ───────────────────
# static/assets/0635-3m/bands.json (tools/make_fob_mockup.py) traces each
# face's top and bottom edge from u=0 (left of the art) to u=1. The imprint
# sits inside that band where the template overlay puts it (about 10%–88% of
# the length, 13%–91% across).
# proof_bounds is a flat stand-in the size of the bent area, which the
# configurator places and scales the art in before bending it.
def _fob_bands():
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent / "static" / "assets" / "0635-3m" / "bands.json"
    try:
        raw = json.loads(p.read_text())
    except Exception:
        return {}, {}
    # Imprint placement on each face, from the template overlay drawn over
    # the photo (2026-10-06): u along the face, v across it (0 = top edge).
    span = {"side1": (0.118, 0.880, 0.13, 0.91), "side2": (0.102, 0.878, 0.15, 0.90)}
    bands, pb = {}, {}
    for sid, b in raw.items():
        u0, u1, v0, v1 = span.get(sid, (0.1, 0.9, 0.125, 0.875))
        bands[sid] = dict(b, u=[u0, u1], v=[v0, v1])
        top, bot = np.asarray(b["top"]), np.asarray(b["bot"])
        mid = (top + bot) / 2
        n = len(mid) - 1
        seg = mid[int(u0 * n):int(round(u1 * n)) + 1]
        length = float(np.hypot(*np.diff(seg, axis=0).T).sum())
        c = seg[len(seg) // 2]
        w, h = round(length), round(length / 4)
        pb[sid] = {"x": int(c[0] - w / 2), "y": int(c[1] - h / 2), "w": w, "h": h}
    return bands, pb


import numpy as np  # noqa: E402
_bands, _pb = _fob_bands()
if _bands:
    PRODUCTS["0635-3m"]["mockup_bands"] = _bands
    PRODUCTS["0635-3m"]["proof_bounds"] = _pb
PRODUCTS["0635-3m"]["shows_inside"] = True


# ── Key Fob 4CP (0635-3w) ──────────────────────────────────────────────────
# Full colour on the Fiery, full bleed over both halves of the strip. The
# print file is the Fiery symbol's page (press/fiery/0635-3w.pdf, 613.159 x
# 92.437 pt): the strip's die plus its bleed, centred. Imprint areas are the
# screen-print fob's (3" x 0.75" each half) moved onto that page; the
# background fills each half to the page edge. Both halves print upright,
# as on the 3m. Mockup: the 3m's photo and bands (static/assets/0635-3w).
_F4_W, _F4_H = 613.159, 92.437
_F4_DX = (_F4_W - 587.52) / 2              # 1-up die → Fiery page
_F4_DY = _F4_H / 2 - (0.26 + 72.5) / 2
_F4_FOLD = (293.913 + _F4_DX) / _F4_W       # fold, as a fraction of the page
_F4_ZONES = {sid: (x + _F4_DX, y + _F4_DY, w, h) for sid, (x, y, w, h) in _FOB_ZONES.items()}
PRODUCTS["0635-3w"] = {
    "label": "Key Fob 4CP - 0635-3w",
    "display_label": "Key Fob 4CP - 0635-3w",
    "material": "neoprene_4cp",
    "has_neoprene": False,
    "has_stitching": False,
    "is_4cp": True,
    "proof_shape": "flat",
    "proof_warp": 0,
    "page_w": _F4_W,
    "page_h": _F4_H,
    "fiery_template": "press/fiery/0635-3w.pdf",
    "template_zones": {sid: {"x": round(x / _F4_W, 4), "y": round((_F4_H - y - h) / _F4_H, 4),
                             "w": round(w / _F4_W, 4), "h": round(h / _F4_H, 4),
                             "l": "Side 1" if sid == "side1" else "Side 2"}
                       for sid, (x, y, w, h) in _F4_ZONES.items()},
    "bleed_zones": {"side1": {"x": 0.0, "y": 0.0, "w": round(_F4_FOLD, 4), "h": 1.0},
                    "side2": {"x": round(_F4_FOLD, 4), "y": 0.0, "w": round(1 - _F4_FOLD, 4), "h": 1.0}},
    "bleed_zone_full": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
    "art_slots": [{"id": sid, "label": "Side 1" if sid == "side1" else "Side 2",
                   "size": '3" W × 0.75" H', "left_pt": round(x, 3), "top_pt": -round(_F4_H - y - h, 3),
                   "w_pt": w, "h_pt": h, "rotation": 0, "shape": "rect"}
                  for sid, (x, y, w, h) in _F4_ZONES.items()],
    "side2_turn": 0,
    "asset_id": "0635-3w",
    "sku": "0635-3w",
    "item_prefix": "0635-3W",
    # The inside of a printed fob is the white neoprene's black back and core.
    "shows_inside": True,
    "inside_colors": {"back": "#0A0A0A", "foam": "#0F0F0F"},
}
if _bands:
    PRODUCTS["0635-3w"]["mockup_bands"] = _bands
    PRODUCTS["0635-3w"]["proof_bounds"] = _pb
PRODUCTS["0635-3m"]["side2_turn"] = 0


# The key fob is always sewn in black thread (no picker; named on the proof).
PRODUCTS["0635-3m"]["stitch_fixed"] = {"name": "Black", "hex": "#1C1C1C"}

# 0472 bottom: the imprint is a 1.5" circle (confirmed 2026-10-06). The
# template's circle measures 1.671" (120.3 pt), which is the outer guide; the
# zone and slot are set to the 1.5" circle on the same centre, so the
# configurator shows and fits the bottom art at the size it prints.
for _pid in ("0472", "0472-24HR-1c", "0472-4CP"):
    _p = PRODUCTS.get(_pid)
    if not _p:
        continue
    _z = _p["template_zones"]["bottom"]
    _W, _H = _p["page_w"], _p["page_h"]
    _nw, _nh = 108.0 / _W, 108.0 / _H
    _p["template_zones"]["bottom"] = dict(_z, x=round(_z["x"] + (_z["w"] - _nw) / 2, 4),
                                         y=round(_z["y"] + (_z["h"] - _nh) / 2, 4),
                                         w=round(_nw, 4), h=round(_nh, 4))
    for _s in _p.get("art_slots", []):
        if _s["id"] == "bottom" and abs(_s["w_pt"] - 108.0) > 0.5:
            _d = (_s["w_pt"] - 108.0) / 2
            _s["left_pt"] = round(_s["left_pt"] + _d, 3)
            _s["top_pt"] = round(_s["top_pt"] - _d, 3)
            _s["w_pt"] = _s["h_pt"] = 108.0
            _s["size"] = '1.5" diameter'


# ── 3-Way Pen (0845) on the Mimaki ─────────────────────────────────────────
# Prints on the Mimaki like the jotter: the export stamps each side into the
# 88 pens of the jig (press/mimaki/0845-jig.json, from the "0845 Mix & Match
# Pen Template"), one file per side — SIDE1 carries Barrel Side 1 + Clip Side
# 1, SIDE2 the other face — with the jotter's hand rule: RH (standard) turns
# Side 1 180 deg in every box, LH turns Side 2. The barrel goes in each pen's
# "BOTTOM HALF" box, the clip in its "TOP HALF" box. The print file is only
# the source the jig files are cut from, so both sides sit upright in it and
# the jig does the turning.
_pen = PRODUCTS.get("0845")
if _pen:
    _pen["mimaki_jig"] = "press/mimaki/0845-jig.json"
    _names = {"barrel_side1": "Barrel Side 1", "clip_side1": "Clip Side 1",
              "barrel_side2": "Barrel Side 2", "clip_side2": "Clip Side 2"}
    for _k, _z in _pen["template_zones"].items():
        _z["l"] = _names.get(_k, _z.get("l"))
    for _s in _pen["art_slots"]:
        _s["label"] = _names.get(_s["id"], _s["label"])
        _s["rotation"] = 0


# ── Le Pen (0844) on the Mimaki ────────────────────────────────────────────
# One imprint, on the face opposite the Le Pen / Made in Japan / Marvy logo:
# 3.125" x 0.18" (225 x 12.96 pt), centred on the jig template's "CENTER OF
# ART" box. Prints on the Mimaki like the jotter: the export stamps it into
# the 100 pens of the jig (press/mimaki/0844-jig.json, from "0844 - LePen
# Template Symbols"), one SIDE1 file, turned 180 deg in every box for RH (the
# standard) and upright for LH. Colours: Le Pen's own 20 (engine.LE_PEN, each
# with its PMS from the NetSuite colour master); the writing ink matches the
# barrel. Mockup: static/assets/0844 (2400 px layers; the top pen shows the
# imprint side, the bottom pen the logo side).
# Template zone: fractions of the 1-up (530.967 x 220.626 pt); the CENTER OF
# ART box's centre is (314.25, 76.875) pt. proof_bounds: the same rect on the
# 1350 px proof canvas (2.432 px/pt, measured pen to pen against the mask).
PRODUCTS["0844"] = {
    "label":         "Le Pen - 0844",
    "material":      "jotter",
    "pen_colors":    "le_pen",
    "has_neoprene":  False,
    "has_stitching": False,
    "proof_shape":   "flat",
    "proof_warp":    0,
    "proof_imprint_inset": {"side1": {"t": 0.0, "r": 0.0, "b": 0.0, "l": 0.0}},
    "ink_black_only": [],
    "writing_ink":   "barrel",
    "ink_fixed":     True,
    "page_w":        225.0,
    "page_h":        12.96,
    "mimaki_jig":    "press/mimaki/0844-jig.json",
    "template_zones": {
        "side1": {"x": round((314.25 - 112.5) / 530.967, 4), "y": round((76.875 - 6.48) / 220.626, 4),
                  "w": round(225.0 / 530.967, 4), "h": round(12.96 / 220.626, 4), "l": "Imprint"},
    },
    "proof_bounds": {"side1": {"x": 527, "y": 538, "w": 547, "h": 32}},
    "bleed_zones": {},
    "art_slots": [
        {"id": "side1", "label": "Imprint", "size": "3.125\" W × 0.18\" H",
         "left_pt": 0.0, "top_pt": 0.0, "w_pt": 225.0, "h_pt": 12.96,
         "rotation": 0, "shape": "rect"},
    ],
}


# ── 3-Way Pen (0845) box label ─────────────────────────────────────────────
# A 2.75" square label at 270 ppi (743 px), exported as a PNG with the files.
# Layers from Numo (static/assets/0845/label): base (arc text, gradient
# panel, white pen), barrel / clip / plunger (pen part + its numbered badge
# and heading, recoloured to the part's colour), title ("3-WAY PEN" and the
# plunger tip), qty ("QTY:"). Variable: the three colour names and the
# quantity (the NetSuite order line's, or the export's QTY field). "QTY: n" is
# centred as one line, so the QTY: layer slides left as the number grows.
# Fonts: label/fonts/name.woff and qty.woff — stand-ins until Numo's own are
# dropped in under the same names. Positions are canvas px, cap tops.
if PRODUCTS.get("0845"):
    PRODUCTS["0845"]["pen_label"] = {
        "dir": "label", "px": 743, "size_in": 2.75, "ppi": 270,
        "names": {"barrel": [333, 165], "clip": [333, 246], "button": [333, 327]},
        "name_cap": 14, "name_max_w": 380, "name_color": "#000000",
        "qty": {"center_x": 369.5, "top": 656, "cap": 31, "gap": 21,
                "layer_left": 314, "layer_right": 424, "color": "#316064"},
    }


# ── Stick Pen (0846) on the Mimaki ─────────────────────────────────────────
# One imprint, on the clip (cap): the jig's art box, 98.80 x 18.07 pt
# (1.37" x 0.25"), centred where the 1-up's "Imprint" box is. (The 1-up's box
# is 103.7 pt wide; the jig's 98.8 pt is what prints, so that is the limit.)
# Export: one SIDE1 file stamped into the 90 pens of the jig
# (press/mimaki/0846-jig.json), RH turned 180 deg, LH upright, as the 0844.
# Colours: the 7 stock colours (engine.STICK_PEN); the mockup is Numo's photo
# of the picked colour (manifest "color_photos"), and the writing ink is that
# colour's own ink (STICK_PEN_INK), not the plastic.
# Template zone: fractions of the 1-up (701.166 x 336.472 pt), box centre
# (508.60, 167.69) pt from the top-left. proof_bounds: the cap's centre in the
# photos at 4.26 px/pt (cap length 121.2 pt = 516 px of 2664), on 1350 px.
PRODUCTS["0846"] = {
    "label":         "Stick Pen - 0846",
    "material":      "jotter",
    "pen_colors":    "stick_pen",
    "has_neoprene":  False,
    "has_stitching": False,
    "proof_shape":   "flat",
    "proof_warp":    0,
    "proof_imprint_inset": {"side1": {"t": 0.0, "r": 0.0, "b": 0.0, "l": 0.0}},
    "ink_black_only": [],
    "ink_fixed":     True,
    "page_w":        98.797,
    "page_h":        18.074,
    "mimaki_jig":    "press/mimaki/0846-jig.json",
    "template_zones": {
        "side1": {"x": round((508.60 - 49.3985) / 701.166, 4), "y": round((167.69 - 9.037) / 336.472, 4),
                  "w": round(98.797 / 701.166, 4), "h": round(18.074 / 336.472, 4), "l": "Clip"},
    },
    "proof_bounds": {"side1": {"x": 207, "y": 649, "w": 213, "h": 39}},
    "bleed_zones": {},
    "art_slots": [
        {"id": "side1", "label": "Clip", "size": "1.37\" W × 0.25\" H",
         "left_pt": 0.0, "top_pt": 0.0, "w_pt": 98.797, "h_pt": 18.074,
         "rotation": 0, "shape": "rect"},
    ],
}


# ── Horizontal Bank Bag 10.5" x 5.5" (9210-02) ─────────────────────────────
# Two item numbers, one bag: 9210-02-EV-1C (expanded vinyl, 12 colours) and
# 9210-02-LN-1C (laminated nylon, 6). Same die, 1-up and mass export; only
# the material colours differ. One-colour screen print, Side 1 (Front) and
# Side 2 (Back), each 9" x 4" centred on its 10.5" x 5.5" panel. Zipper and
# stitching are always black (no options). Press: press/9210-02-1C.pdf +
# press_spec_9210-02.json (DBG 2-up and DISCO 1-up, a Front and a Back sheet
# each). Mockup: static/assets/9210-02 (placeholder until Numo's layers).
# Template zones: fractions of the 1-up (1585 x 469 pt, top-down).
_BB_W, _BB_H = 1585.0, 469.0
def _bank_bag(pid, label, material):
    return {
        "label":         label,
        "material":      material,
        "asset_id":      "9210-02",
        "base_id":       "9210-02",
        "is_screenprint": True,          # one colour: the 1C artwork rules and press sheets
        "program":       "Standard",     # ...but not a This Is Fast (24 HR) item
        "has_neoprene":  False,
        "has_stitching": False,
        "stitch_fixed":  {"name": "Black", "hex": "#1C1C1C"},
        "proof_shape":   "flat",
        "proof_warp":    0,
        "page_w":        _BB_W,
        "page_h":        _BB_H,
        "template_zones": {
            "side1": {"x": round(844.25 / _BB_W, 4), "y": round(98.36 / _BB_H, 4),
                      "w": round(648 / _BB_W, 4), "h": round(288 / _BB_H, 4), "l": "Side 1 (Front)"},
            "side2": {"x": round(92.75 / _BB_W, 4), "y": round(98.36 / _BB_H, 4),
                      "w": round(648 / _BB_W, 4), "h": round(288 / _BB_H, 4), "l": "Side 2 (Back)"},
        },
        "proof_bounds": {
            "side1": {"x": 719, "y": 559, "w": 552, "h": 245},
            "side2": {"x": 79,  "y": 559, "w": 552, "h": 245},
        },
        "bleed_zones": {},
        "art_slots": [
            {"id": "side1", "label": "Side 1 (Front)", "size": "9\" W × 4\" H",
             "left_pt": 844.25, "top_pt": -98.36, "w_pt": 648.0, "h_pt": 288.0, "rotation": 0, "shape": "rect"},
            {"id": "side2", "label": "Side 2 (Back)", "size": "9\" W × 4\" H",
             "left_pt": 92.75, "top_pt": -98.36, "w_pt": 648.0, "h_pt": 288.0, "rotation": 0, "shape": "rect"},
        ],
    }
PRODUCTS["9210-02-EV-1C"] = _bank_bag("9210-02-EV-1C", "Horizontal Bank Bag EV 10.5 x 5.5 - 9210-02-EV-1C", "expanded_vinyl")
PRODUCTS["9210-02-LN-1C"] = _bank_bag("9210-02-LN-1C", "Horizontal Bank Bag LN 10.5 x 5.5 - 9210-02-LN-1C", "laminated_nylon")
# Numo's photo mockups (2026-10-07), one set per material: top bag = Side 1
# (Front), bottom bag = Side 2 (Back). proof_bounds: the 9" x 4" imprint on
# each bag, from the colour mask's body (10.5" wide) on the 1350 px canvas,
# 0.095" below the body's centre as on the 1-up.
# "press_tag": burned into every screen beside the NSO number so production
# pulls the right goods (one template serves both materials).
PRODUCTS["9210-02-EV-1C"].update({
    "asset_id": "9210-02-EV", "press_tag": "EV",
    "proof_bounds": {"side1": {"x": 192, "y": 291, "w": 627, "h": 279},
                     "side2": {"x": 531, "y": 792, "w": 627, "h": 279}},
})
PRODUCTS["9210-02-LN-1C"].update({
    "asset_id": "9210-02-LN", "press_tag": "LN",
    "proof_bounds": {"side1": {"x": 210, "y": 240, "w": 603, "h": 268},
                     "side2": {"x": 508, "y": 781, "w": 603, "h": 268}},
})
SCREENPRINT_PRODUCT_IDS |= {"9210-02-EV-1C", "9210-02-LN-1C"}


# ── 0799-3m Liam Can Insulator ─────────────────────────────────────────────
# Two cuts sewn together: one long neoprene panel with a single side seam,
# sewn to a bottom circle; the raw top edge is bound in a coloured bias the
# customer picks ("trim"). Imprints: Side 1 and Side 2 opposite each other on
# the panel, or one side alone at the panel's centre, opposite the seam
# ("one_side_zone" / "one_side_bounds": where Side 1 moves when Side 2 is
# empty); bottom circle optional, printed on its own sheets.
# Template space = the guide page of press/0799-3m.pdf, cropped to the drawing
# (x 30-670, y 600-1140 pt); press geometry in press/press_spec_0799-3m.json
# (tools/make_0799_template.py); assets from tools/make_0799_assets.py —
# the mockup is a flat PLACEHOLDER until Numo's photo layers arrive.
_LI_X0, _LI_TOP = 30.0, 1140.0
_LI_SLOTS = [
    ("side1", "Side 1", '3" W × 3" H', 42.5625 + 154.44 - 108, 973.07 + 108, 216.0, "rect"),
    ("bottom", "Bottom", '1.8" diameter', 350.0 - 64.8, 700.0 + 64.8, 129.6, "circle"),
    ("side2", "Side 2", '3" W × 3" H', 42.5625 + 460.44 - 108, 973.07 + 108, 216.0, "rect"),
]
PRODUCTS["0799-3m"] = {
    "label": "Liam Can Insulator - 0799-3m",
    "display_label": "Liam Can Insulator - 0799-3m",
    "material": "neoprene",
    "has_neoprene": True,
    "has_stitching": True,
    "trim": {"label": "Bias", "palette": "bias", "mask": "bias_mask"},
    "proof_shape": "cylinder",
    "proof_warp": 70,
    # The print areas (art_zone_*) are the 3" imprint as photographed, so no
    # inset; the wrap is read from their shape.
    "proof_imprint_inset": 0,
    "page_w": 640.0,
    "page_h": 540.0,
    "template_zones": {
        "side1": {"x": 0.0922, "y": 0.1091, "w": 0.3375, "h": 0.4, "l": "Side 1"},
        "bottom": {"x": 0.3987, "y": 0.6948, "w": 0.2025, "h": 0.24, "l": "Bottom"},
        "side2": {"x": 0.5703, "y": 0.1091, "w": 0.3375, "h": 0.4, "l": "Side 2"},
    },
    "one_side_zone": {"x": 0.3312, "y": 0.1091, "w": 0.3375, "h": 0.4, "l": "Side 1"},
    # Two photo sets (static/assets/0799-3m, -1s): both fronts for two sides;
    # the front and the seam side when Side 1 prints alone.
    "one_side_assets": "0799-3m-1s",
    "bleed_zones": {},
    "art_slots": [{"id": sid, "label": lab, "size": size, "left_pt": round(x - _LI_X0, 3),
                   "top_pt": -round(_LI_TOP - top, 3), "w_pt": w, "h_pt": w, "rotation": 0, "shape": shape}
                  for sid, lab, size, x, top, w, shape in _LI_SLOTS],
    "asset_id": "0799-3m",
    "sku": "0799-3m",
    "item_prefix": "0799",
}
if "0799-3m" not in PMS_ASSIGN_PRODUCT_IDS:
    PMS_ASSIGN_PRODUCT_IDS.append("0799-3m")

# ── Lifestyle view (2026-10-08) ──────────────────────────────────────────────
# A lifestyle photo with the customer's own art on the insulator, behind the
# configurator's "Lifestyle" button. 0070-3m only for now; set after every
# copy of the 0070-3m above so its twins don't inherit it.
PRODUCTS["0070-3m"]["lifestyle_assets"] = "0070-3m-life"


# ── Item numbers that name the same item ────────────────────────────────────
#
# The Main Squeeze tote's item number changed in NetSuite: 5001-7 and 5001-10
# are the same bag, and orders come in under either. The second number is the
# same item - same mockup, imprint areas and press set-up - so an order line
# for it opens, and its files carry the number on the order. Copied last, from
# the finished item, so a change to one always reaches the other. Not listed
# again in the catalog ("alias_of").
ITEM_NUMBER_ALIASES = {
    "5001-10": "5001-7",
}
for _alias, _target in ITEM_NUMBER_ALIASES.items():
    if _target in PRODUCTS and _alias not in PRODUCTS:
        _a = copy.deepcopy(PRODUCTS[_target])
        _lab = _a.get("label") or _target
        _a.update({
            "label":    _lab[:-len(_target)] + _alias if _lab.endswith(_target) else f"{_lab} ({_alias})",
            "asset_id": _a.get("asset_id") or _target,
            "alias_of": _target,
        })
        PRODUCTS[_alias] = _a
