#!/usr/bin/env python3
import curses, random, time, math, json, locale, argparse, os
from collections import deque, namedtuple
locale.setlocale(locale.LC_ALL, '')
# Configuration / Limits
DEFAULT_SPEED = 1.0        # movement visual speed (not warp multiplier)
MIN_SPEED = 0.3
MAX_SPEED = 4.0
VISUAL_SPEED_CAP = 2.0     # cap for smooth star visuals
FPS = 28.0
Z_MAX = 8.0
STAR_DENSITY = 160
POWER_SPAWN_CHANCE = 0.0015
POWER_LIFE = 12.0
POWER_COLLECT_RADIUS = 2
WARP_DURATION = 3.5         # warp cinematic duration
WARP_FUEL_MULT = 3.5        # warp consumes this multiplier of normal fuel
FUEL_MAX = 1000.0
FUEL_CONSUMPTION_MOVE = 0.08    # per second
FUEL_CONSUMPTION_SCAN = 5.0
FUEL_CONSUMPTION_PICK = 2.0
TASK_REWARD_BASE = 200
SCAN_RADIUS = 3.0
GALAXY_DB = {
    "Andromeda": {
        "type": "Spiral", "distance": "2.5 Mly", "faction": "Andromedan Union",
        "art": ["   .   *    .", "  *  🌀  .  *", "   .    *   "]
    },
    "Sombrero": {
        "type": "Elliptical", "distance": "29 Mly", "faction": "Sombrero Coalition",
        "art": ["  .---. 🌀", " /     \\", " \\_____/ "]
    },
    "Whirlpool": {
        "type": "Barred Spiral", "distance": "23 Mly", "faction": "Independent",
        "art": ["  .-'-.", " ( 🌀 )", "  `-.-'"]
    },
    "Triangulum": {
        "type": "Spiral", "distance": "3 Mly", "faction": "Triangulum Pact",
        "art": ["   /\\  ", "  /🌀\\ ", " /__\\ "]
    },
    "MilkyWay-Neighbor": {
        "type": "Irregular", "distance": "0.8 Mly", "faction": "None",
        "art": ["  * . *", "  . 🌀 .", "  * . *"]
    }
}
GALAXY_NAMES = list(GALAXY_DB.keys())
SHIP_VARIANTS = [
    ["  /\\  ", " /==\\ ", "/_||_\\"],
    ["   /^\\   ", "  /_=_\\  ", " /_/ \\_\\"],
    ["   __/\\__  ", "  /-====-\\ ", "   \\____/  "],
    ["   __|__  ", "  /_/ \\_\\ ", "   \\_=_/  "]
]
PLANET_ARTS = [
    ["  _~_ ", " (   )", "  '-' "],
    ["  .-. ", " ( O )", "  '-' "],
    ["  ___ ", " ( o )", "  '_' "],
    ["  *** ", " * O *", "  *** "]
]
# Classes / Objects
class Star:
    __slots__ = ("x","y","z","ch","col")
    def __init__(self,w,h): self.reset(w,h,init=True)
    def reset(self,w,h,init=False):
        self.x = (random.random()-0.5)*w
        self.y = (random.random()-0.5)*h
        self.z = random.uniform(0.5, Z_MAX) if init else Z_MAX
        self.update()
    def update(self):
        depth = self.z / Z_MAX
        if depth < 0.3: self.ch, self.col = "✦", 3
        elif depth < 0.6: self.ch, self.col = "+", 2
        else: self.ch, self.col = ".", 1
    def step(self, visual_speed, dt):
        self.x += math.sin(time.time()*0.3 + self.z)*0.08*dt
        # move based on visual speed (clamped)
        self.z -= dt * max(0.15, visual_speed / (1 + self.z*0.12))
        self.update()
        return self.z > 0.1
class GalaxySprite:
    __slots__ = ("name","art","x","y","z","w","h")
    def __init__(self,name,art,w,h):
        self.name=name; self.art=art; self.w=w; self.h=h; self.reset()
    def reset(self):
        self.x = (random.random()-0.5)*self.w*0.6
        self.y = (random.random()-0.5)*self.h*0.6
        self.z = Z_MAX
    def step(self, visual_speed, dt):
        self.z -= dt * visual_speed * 0.22
        return self.z > 0.12

class PowerPack:
    __slots__ = ("x","y","t0")
    def __init__(self,x,y):
        self.x=x; self.y=y; self.t0=time.time()
# For mission modeling
Planet = namedtuple("Planet", ["name","type","atmos","life","desc","art"])
StarSystem = namedtuple("StarSystem", ["name","x","y","planets","history","threat"])
# Utility drawing helpers
def safe_addstr(win, y, x, s, col=0, attr=0):
    """
    Safe add string with optional color pair index and curses attributes (like A_BOLD, A_BLINK).
    Backwards-compatible: existing callers passing col still work.
    """
    try:
        maxy, maxx = win.getmaxyx()
        if y < 0 or y >= maxy: return
        if x >= maxx: return
        if x < 0:
            s = s[-x:]
            x = 0
        if x + len(s) > maxx:
            s = s[:maxx - x]
        attr_mask = curses.color_pair(col) | (attr or 0)
        win.addstr(y, x, s, attr_mask)
    except Exception:
        return
def draw_box(win, top, left, w, h, title=None, col=2):
    if w < 4 or h < 3: return
    safe_addstr(win, top, left, "┌" + "─"*(w-2) + "┐", col)
    for i in range(1,h-1):
        safe_addstr(win, top+i, left, "│" + " "*(w-2) + "│", col)
    safe_addstr(win, top+h-1, left, "└" + "─"*(w-2) + "┘", col)
    if title:
        safe_addstr(win, top, left+2, f"[ {title} ]", col)

# Procedural generation
def make_planet(idx):
    art = random.choice(PLANET_ARTS)
    return Planet(
        name=f"Planet-{chr(65+idx)}",
        type=random.choice(["Terrestrial","Gas Giant","Ice","Oceanic","Volcanic","Desert"]),
        atmos=random.choice(["N₂/O₂","CO₂","H₂/He","Thin","Toxic"]),
        life=random.choice(["None","Microbial","Simple","Complex"]),
        desc=random.choice(["Rocky world","Ringed giant","Frozen cliffs","Deep oceans","Volcanic plains","Bright sands"]),
        art=art
    )
def make_star_system(i, w, h):
    # place x,y within screen bounds
    x = random.randint(6, max(6, w-8))
    y = random.randint(4, max(4, h-6))
    name = f"Sys-{random.choice(['Alfa','Beta','Delta','Sigma','Zeta','Tau'])}-{i}"
    planets = [make_planet(j) for j in range(random.randint(1,4))]
    history = random.choice([
        f"{name} once hosted ancient probes.",
        f"{name} is known for crystal nebulae.",
        f"{name} holds ruined orbital platforms.",
        f"{name} has a stable binary pair that affects tides."
    ])
    # occasional threat
    threat = random.choice([None, "Radiation Storm", "Pirate Drones", None, None])
    return StarSystem(name=name, x=x, y=y, planets=planets, history=history, threat=threat)
def setup_galaxy_mission(galaxy_name, w, h):
    # Each galaxy mission has 4-6 star systems and a list of tasks
    n = random.randint(4,6)
    systems = [make_star_system(i+1, w, h) for i in range(n)]
    # choose 2-3 systems as mission targets with tasks
    targets = random.sample(systems, k=max(2, n//2))
    tasks = []
    for s in targets:
        task_type = random.choice(["Scan for life","Analyze composition","Collect sample","Map magnetosphere"])
        tasks.append({"system": s.name, "task": task_type, "done": False, "reward": TASK_REWARD_BASE})
    mission = {"galaxy": galaxy_name, "systems": systems, "tasks": tasks, "assigned_by": "Earth Command"}
    return mission
# AI Copilot & Logs
AI_HINTS = [
    "Sensors detect a faint signal ahead.",
    "Recommend scanning the nearby system.",
    "Warp vector alignment nominal.",
    "Energy signature from uncharted debris.",
    "Suggest collecting the glowing caches."
]
COPILOT_PERSONA = [
    "AI: Scanning for microbiosignatures... standby.",
    "AI: Logging historical records for this star system.",
    "AI: Threat scanners nominal, but remain vigilant."
]

# Save report helpers
def save_report(report, fname_json="mission_report.json", fname_txt="mission_report.txt"):
    try:
        with open(fname_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    try:
        with open(fname_txt, "w", encoding="utf-8") as f:
            f.write("MISSION REPORT\n")
            f.write(json.dumps(report, indent=2, ensure_ascii=False))
    except Exception:
        pass

# Visual warp scene (cinematic)
def warp_cinematic(win, duration=WARP_DURATION):
    h,w = win.getmaxyx()
    start = time.time()
    msg = "🚀 WARP ENGAGED 🚀"
    while time.time() - start < duration:
        win.erase()
        for _ in range(80):
            try:
                y = random.randint(0, max(0,h-1))
                x = random.randint(0, max(0,w-1))
                safe_addstr(win, y, x, random.choice(["/", "\\", "|", "-"]), random.choice([2,3,4]))
            except Exception:
                pass
        safe_addstr(win, h//2, max(0,(w - len(msg))//2), msg, 3)
        win.refresh()
        time.sleep(0.06)
    win.erase(); win.refresh()

# Main run loop
def run(stdscr, init_speed, density):
    # initialize curses
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_CYAN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_MAGENTA, -1)
    curses.init_pair(5, curses.COLOR_RED, -1)
    # Blue for important splash prompts
    try:
        curses.init_pair(6, curses.COLOR_BLUE, -1)
    except Exception:
        # some terminals may not support all colors; ignore failures
        pass

    random.seed()
    # state
    speed = max(MIN_SPEED, min(MAX_SPEED, init_speed))
    visual_speed = min(speed, VISUAL_SPEED_CAP)
    density = max(30, density)
    h,w = stdscr.getmaxyx()
    stars = [Star(w,h) for _ in range(density)]
    galaxy_sprites = deque()
    power_packs = []
    cur_galaxy_idx = random.randrange(len(GALAXY_NAMES))
    cur_galaxy = GALAXY_NAMES[cur_galaxy_idx]
    # set up mission for current galaxy
    mission = setup_galaxy_mission(cur_galaxy, w, h)
    missions_completed = []
    visited_report = {name: {"type": GALAXY_DB[name]["type"], "systems": []} for name in GALAXY_NAMES}
    score = 0
    fuel = FUEL_MAX
    energy_consumed = 0.0
    dist_traveled = 0.0
    show_ai = False
    show_map = False
    show_missions = False
    show_log = False
    copilot_msg = "AI: Systems online. Earth Command standing by."
    copilot_timer = 0.0
    crew_logs = ["Captain's Log: Voyager commissioned.", "Engineer: Fusion cores stable.", "XO: Crew ready."]
    last_hint_time = 0
    last_time = time.time()
    ship_art = random.choice(SHIP_VARIANTS)
    ship_x = w//2
    ship_y = h//2
    warp_active = False
    warp_start = 0.0

    # SPLASH - Mission objectives from Earth Command
    def splash_screen(win, mission):
        win.nodelay(False)
        win.erase()
        hh, ww = win.getmaxyx()
        heading = "VOYAGER - Galactic Odyssey" 
        hb_w = min(ww - 4, max(len(heading) + 6, 30))
        hb_left = max(2, (ww - hb_w) // 2)
        hb_top = max(1, hh//2 - 30)
        draw_box(win, hb_top, hb_left, hb_w, 3, title=None, col=5)
        safe_addstr(win, hb_top + 1, hb_left + (hb_w - len(heading)) // 2, heading, 5)
        title = "EARTH COMMAND - MISSION BRIEF"
        safe_addstr(win, max(1,hh//2 - 15), max(0,(ww - len(title))//2), title, 2)
        lines = [
            f"Hello! Commander of the Voyager",
            "",
            f"Here is your next mission....",
            "",
            f"Galaxy: {mission['galaxy']}",
            "",
            "Objectives:",
            ""
        ]
        for t in mission["tasks"]:
            lines.append(f" - {t['task']} @ {t['system']} (Reward: {t['reward']})")
        lines.append("")
        lines.append("Press any key to accept mission and commence launch...")
        top = max(3, hh//2 - len(lines))
        for i, L in enumerate(lines):
            x = max(4, (ww - 60)//2)
            text = L[:60]
            
            if text.strip().startswith("Press any key"):
                # Show the prompt in bold blue 
                safe_addstr(win, top + i, x, text, 6, curses.A_BOLD)
            else:
                safe_addstr(win, top + i, x, text, 3 if i>1 else 1)
        win.refresh()
        win.getch()
        win.erase(); win.refresh()
        win.nodelay(True)

    # Show splash 
    splash_screen(stdscr, mission)
    safe_addstr(stdscr, h//2, max(0,(w - 40)//2), f"Entering {cur_galaxy}... {random.choice(['Be vigilant.','Good luck, Captain.'])}", 3)
    stdscr.refresh(); time.sleep(1.0)

    running = True
    while running:
        now = time.time()
        dt = now - last_time if last_time else 0.033
        last_time = now

        h,w = stdscr.getmaxyx()
        stdscr.erase()
        if h < 20 or w < 70:
            safe_addstr(stdscr, 1, 2, "Terminal too small — resize to at least 70x20", 5)
            safe_addstr(stdscr, 3, 2, "Press Q to quit.", 3)
            stdscr.refresh()
            try:
                k = stdscr.getch()
                if k in (ord('q'), ord('Q'), 27):
                    running = False
            except Exception:
                pass
            time.sleep(0.3)
            continue

        # input handling
        try:
            k = stdscr.getch()
        except Exception:
            k = -1
        moved = False
        if k != -1:
            if k in (ord('q'), ord('Q'), 27):
                running = False; break
            elif k in (curses.KEY_LEFT, ord('a'), ord('A')):
                ship_x = max(2, ship_x - 1); moved = True
            elif k in (curses.KEY_RIGHT, ord('d'), ord('D')):
                ship_x = min(w - SHIP_VARIANTS[0].__len__() - 2, ship_x + 1); moved = True
            elif k in (curses.KEY_UP, ord('w'), ord('W')):
                ship_y = max(2, ship_y - 1); moved = True
            elif k in (curses.KEY_DOWN, ord('s'), ord('S')):
                ship_y = min(h- SHIP_VARIANTS[0].__len__() - 3, ship_y + 1); moved = True
            elif k in (ord('+'), ord('=')):
                speed = min(MAX_SPEED, speed + 0.2)
            elif k in (ord('-'), ord('_')):
                speed = max(MIN_SPEED, speed - 0.2)
            elif k in (ord('i'), ord('I')):
                show_ai = not show_ai
            elif k in (ord('g'), ord('G')):
                show_map = not show_map
            elif k in (ord('l'), ord('L')):
                show_log = True
            elif k in (ord('p'), ord('P')):
                # pick up power pack if near
                picked = None
                for pp in power_packs:
                    if abs(pp.x - ship_x) <= POWER_COLLECT_RADIUS and abs(pp.y - ship_y) <= POWER_COLLECT_RADIUS:
                        picked = pp; break
                if picked:
                    try: power_packs.remove(picked)
                    except Exception: pass
                    score += 100
                    fuel = min(FUEL_MAX, fuel + 60.0)
                    energy_consumed += FUEL_CONSUMPTION_PICK
                    copilot_msg = "ANDROID AI: Power cache secured. Energy redistributed."
                    copilot_timer = now
            elif k in (ord('s'),):  # lowercase s handled by movement, detect uppercase 'S' as ord('S')
                # handled above; to implement scanning we map capital 'X' to Scan to avoid conflict
                pass
            elif k in (ord('S'),):  # likely not seen by curses; include scan mapping to space and 'x'
                pass
            elif k in (ord('x'), ord('X'), ord(' ')):  # scan / sample
                # find nearest star system within radius; iterate systems
                performed = False
                for sys in mission["systems"]:
                    # use Euclidean distance so scan reaches in a radius around the ship
                    dx = sys.x - ship_x
                    dy = sys.y - ship_y
                    if math.hypot(dx, dy) <= SCAN_RADIUS:
                        # consume fuel and do task if any tasks target this system
                        if fuel >= FUEL_CONSUMPTION_SCAN:
                            fuel -= FUEL_CONSUMPTION_SCAN
                            energy_consumed += FUEL_CONSUMPTION_SCAN
                            # reveal history and possibly mark tasks
                            # check tasks in mission
                            for t in mission["tasks"]:
                                if t["system"] == sys.name and not t["done"]:
                                    t["done"] = True
                                    reward = t.get("reward", TASK_REWARD_BASE)
                                    score += reward
                                    copilot_msg = f"ANDROID AI: Task '{t['task']}' completed at {sys.name}. +{reward} pts."
                                    copilot_timer = now
                                    performed = True
                                    # record visited
                                    visited_report[cur_galaxy]["systems"].append({"system": sys.name, "task": t["task"]})
                                    break
                            if not performed:
                                # generic scan: small reward for discovering info
                                score += 20
                                copilot_msg = f"ANDROID AI: Scanned {sys.name}. {sys.history}"
                                copilot_timer = now
                                performed = True
                        else:
                            copilot_msg = "ANDROID AI: Insufficient fuel to scan."
                            copilot_timer = now
                        break
                if not performed:
                    copilot_msg = "ANDROID AI: No nearby system to scan. Move closer to a star-system marker."
                    copilot_timer = now
            elif k in (ord('z'), ord('Z')):  
                # manual warp: consume big fuel and teleport to next galaxy (if fuel)
                needed = FUEL_CONSUMPTION_MOVE * WARP_FUEL_MULT * 4.0
                if fuel >= needed:
                    fuel -= needed
                    energy_consumed += needed
                    copilot_msg = "ANDROID AI: Initiating warp jump. Hold on!"
                    copilot_timer = now
                    warp_cinematic(stdscr, duration=WARP_DURATION)
                    # next galaxy and new mission
                    cur_galaxy_idx = (cur_galaxy_idx + 1) % len(GALAXY_NAMES)
                    cur_galaxy = GALAXY_NAMES[cur_galaxy_idx]
                    # save current mission if any tasks done
                    missions_completed.append(mission)
                    mission = setup_galaxy_mission(cur_galaxy, w, h)
                    # brief entering text
                    safe_addstr(stdscr, h//2, max(0,(w - 40)//2), f"Entering {cur_galaxy}...", 3)
                    stdscr.refresh(); time.sleep(0.9)
                else:
                    copilot_msg = "ANDROID AI: Not enough fuel for warp."
                    copilot_timer = now
        # fuel consumption while moving (approx based on dt)
        # if ship moved in this frame, consume more; but to simplify, we drain per second
        movement_fuel = FUEL_CONSUMPTION_MOVE * dt * (1 + max(0.0, speed - 1.0))
        fuel = max(0.0, fuel - movement_fuel)
        energy_consumed += movement_fuel

        # distance metric (use speed * dt)
        dist_traveled += speed * dt * 0.08

        # spawn powerpacks occasionally
        if random.random() < POWER_SPAWN_CHANCE:
            px = random.randint(6, max(6, w-8))
            py = random.randint(4, max(4, h-6))
            power_packs.append(PowerPack(px, py))

        # star visuals update (use visual_speed cap)
        visual_speed = min(speed, VISUAL_SPEED_CAP)
        for s in stars:
            if not s.step(visual_speed, dt):
                s.reset(w,h, False)
            sx = int((w//2) + (s.x / s.z) * (min(w,h)/2))
            sy = int((h//2) + (s.y / s.z) * (min(w,h)/4))
            if 0 <= sx < w and 0 <= sy < h:
                if warp_active:
                    safe_addstr(stdscr, sy, sx, "|", 2)
                else:
                    safe_addstr(stdscr, sy, sx, s.ch, s.col)

        # occasionally show galaxy sprite
        if random.random() < 0.0009:
            gal_art = GALAXY_DB[cur_galaxy]["art"]
            galaxy_sprites.append(GalaxySprite(cur_galaxy, gal_art, w, h))
        for _ in range(len(galaxy_sprites)):
            g = galaxy_sprites.popleft()
            if g.step(visual_speed, dt):
                gx = int((w//2) + (g.x / g.z) * (min(w,h)/2))
                gy = int((h//2) + (g.y / g.z) * (min(w,h)/4))
                for i, line in enumerate(g.art):
                    safe_addstr(stdscr, gy+i, gx, line, 4)
                galaxy_sprites.append(g)

        # draw star systems (mission systems) as markers
        for sys in mission["systems"]:
            # marker changes if threat present
            color = 5 if sys.threat else 3
            safe_addstr(stdscr, sys.y, sys.x, "◎", color)
            # small label truncated if too long
            safe_addstr(stdscr, sys.y+1, max(0, sys.x - 4), sys.name[:12], 1)
            # draw planet art near system if nearby screen edge permits
            # only draw first planet art small
            try:
                art = sys.planets[0].art
                for i, line in enumerate(art):
                    safe_addstr(stdscr, sys.y+2+i, max(0, sys.x - len(line)//2), line, 2)
            except Exception:
                pass

        # draw power packs (pulse)
        for pp in power_packs[:]:
            if time.time() - pp.t0 > POWER_LIFE:
                try: power_packs.remove(pp)
                except Exception: pass
                continue
            sym = "⚡" if int(time.time()*2) % 2 == 0 else "*"
            safe_addstr(stdscr, pp.y, pp.x, sym, 3)

        # draw ship (centered) - use distinct color from planets (magenta)
        for i, line in enumerate(ship_art):
            safe_addstr(stdscr, ship_y + i, ship_x, line, 4)

        # HUD - Galaxy, Target Star-System (nearest undone task), Fuel, Score
        # find next task target
        next_task = None
        for t in mission["tasks"]:
            if not t["done"]:
                next_task = t; break
        target_text = next_task["system"] if next_task else "None"
        hud_y = 0
        safe_addstr(stdscr, hud_y, 2, f"Galaxy: {cur_galaxy}", 2)
        safe_addstr(stdscr, hud_y, 28, f"Target: {target_text}", 3)
        # fuel bar
        fuel_pct = fuel / FUEL_MAX
        try:
            bar_len = int(fuel_pct * 24)
            bar = "[" + "█"*bar_len + " "*(24-bar_len) + "]"
            safe_addstr(stdscr, hud_y+1, 2, f"Fuel: {bar} {int(fuel)}", 3)
        except Exception:
            safe_addstr(stdscr, hud_y+1, 2, f"Fuel: {int(fuel)}", 3)
        # score and distance
        safe_addstr(stdscr, hud_y, max(0,w-36), f"Score: {score}", 3)
        safe_addstr(stdscr, hud_y+1, max(0,w-36), f"Dist: {dist_traveled:.3f} AU", 4)
        # energy consumed display smaller
        safe_addstr(stdscr, hud_y+2, max(0,w-36), f"Energy used: {int(energy_consumed)}", 1)

        # persistent crew logs (left-top, below HUD)
        try:
            max_logs = 3
            for i, line in enumerate(crew_logs[:max_logs]):
                # clamp length to avoid overlapping right-side panels
                max_len = max(20, min(48, (w//2) - 4))
                safe_addstr(stdscr, hud_y+3 + i, 2, line[:max_len], 3)
        except Exception:
            pass

        # side panel mission brief
        panel_w = min(42, max(28, w//3))
        panel_h = 8
        panel_x = max(2, w - panel_w - 2)
        panel_top = 2
        draw_box(stdscr, panel_top, panel_x, panel_w, panel_h, title="MISSION", col=2)
        safe_addstr(stdscr, panel_top+1, panel_x+2, f"Galaxy: {mission['galaxy']}"[:panel_w-4], 3)
        safe_addstr(stdscr, panel_top+2, panel_x+2, f"Assigned by: {mission.get('assigned_by','Earth')}"[:panel_w-4], 1)
        # tasks list (trimmed)
        for i, t in enumerate(mission["tasks"][:3]):
            status = "✓" if t["done"] else " "
            safe_addstr(stdscr, panel_top+3+i, panel_x+2, f"[{status}] {t['task']} @ {t['system']}"[:panel_w-4], 3 if t["done"] else 1)

        # AI Hints
        if show_ai:
            ai_w = min(48, w - 8)
            draw_box(stdscr, panel_top + panel_h + 1, 2, ai_w, 4, title="AI", col=2)
            if (now - copilot_timer) < 6.0:
                safe_addstr(stdscr, panel_top + panel_h + 2, 4, copilot_msg[:ai_w-6], 4)
            else:
                # periodic hints
                if now - last_hint_time > 4.0 and random.random() < 0.06:
                    copilot_msg = random.choice(COPILOT_PERSONA + AI_HINTS)
                    copilot_timer = now; last_hint_time = now
                safe_addstr(stdscr, panel_top + panel_h + 2, 4, copilot_msg[:ai_w-6], 4)
            
        # mini map
        if show_map:
            map_w = min(36, w//4)
            map_h = min(8, h//4)
            draw_box(stdscr, h - map_h - 4, 2, map_w, map_h, title="GALAXY MAP", col=2)
            for i, name in enumerate(GALAXY_NAMES[:map_h-2]):
                mark = "✅" if visited_report.get(name, {}).get("systems") else "  "
                safe_addstr(stdscr, h - map_h - 3 + i, 4, f"{mark} {name}"[:map_w-4], 3)

        # crew log popup
        if show_log:
            lg_w = min(64, w-8)
            lg_h = 6
            lg_left = max(4, (w - lg_w) // 2)
            lg_top = max(3, (h - lg_h) // 2)
            draw_box(stdscr, lg_top, lg_left, lg_w, lg_h, title="CREW LOG", col=2)
            for i, line in enumerate(crew_logs):
                safe_addstr(stdscr, lg_top+1+i, lg_left+2, line[:lg_w-4], 3)
            show_log = False

        # instructions
        safe_addstr(stdscr, h-1, 2, "(Arrows/WASD move, X=scan, Z=warp, P=pickup, G=GALAXY MAP, I=AI Hints , Q=quit)", 2)
        stdscr.refresh()
        # frame cap
        time.sleep(max(0, 1.0/FPS - (time.time() - now)))
    # compile mission report
    final_report = {
        "missions_completed_count": len([m for m in missions_completed if m]),
        "current_mission": mission["galaxy"],
        "tasks_status": mission["tasks"],
        "visited_report": visited_report,
        "score": score,
        "distance_traveled_AU": round(dist_traveled, 4),
        "energy_consumed": round(energy_consumed, 2),
        "fuel_remaining": round(fuel, 2),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_report(final_report)
    # goodbye screen
    stdscr.erase()
    title = "🖖 MISSION REPORT - EARTH COMMAND 🖖"
    safe_addstr(stdscr, 1, max(0,(w - len(title))//2), title, 2)
    safe_addstr(stdscr, 3, 4, f"Galaxy: {final_report['current_mission']}", 3)
    safe_addstr(stdscr, 4, 4, f"Score: {final_report['score']}", 3)
    safe_addstr(stdscr, 5, 4, f"Distance (AU): {final_report['distance_traveled_AU']}", 1)
    safe_addstr(stdscr, 6, 4, f"Energy consumed: {final_report['energy_consumed']}", 1)
    safe_addstr(stdscr, 7, 4, f"Saved mission_report.json / .txt", 2)
    safe_addstr(stdscr, h-2, max(0,(w - 28)//2), "Press any key to exit.", 4)
    stdscr.nodelay(False)
    try:
        stdscr.getch()
    except Exception:
        pass
# Entrypoint
def main():
    parser = argparse.ArgumentParser(prog="voyage_starfield_odyssey")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    parser.add_argument("--density", type=int, default=STAR_DENSITY)
    args = parser.parse_args()
    try:
        curses.wrapper(run, args.speed, args.density)
    except KeyboardInterrupt:
        try:
            curses.endwin()
        except Exception:
            pass
        print("\nExited safely 🖖")
    except Exception as e:
        try:
            with open("voyage_error.log", "w", encoding="utf-8") as f:
                f.write(str(e))
        except Exception:
            pass
        try:
            curses.endwin()
        except Exception:
            pass
        print("An unexpected error occurred. See voyage_error.log if available. Exiting.")

if __name__ == "__main__":
    main()