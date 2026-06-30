#!/usr/bin/env python3
"""Read car/person poses from gz topic and print SDF-ready pose lines."""
import sys, re, math

text = sys.stdin.read()
blocks = re.split(r'(?=  name: ")', text)

for blk in blocks:
    m = re.search(r'name: "([^"]+)"', blk)
    if not m:
        continue
    name = m.group(1)
    if not re.match(r'(car|person)_\d+$', name):
        continue

    m_pos = re.search(
        r'position \{[^}]*\bx: ([^\n]+)\n[^}]*\by: ([^\n]+)\n[^}]*\bz: ([^\n]+)',
        blk, re.DOTALL)
    m_ori = re.search(
        r'orientation \{[^}]*\bx: ([^\n]+)\n[^}]*\by: ([^\n]+)\n[^}]*\bz: ([^\n]+)\n[^}]*\bw: ([^\n]+)',
        blk, re.DOTALL)

    px = float(m_pos.group(1).strip()) if m_pos else 0
    py = float(m_pos.group(2).strip()) if m_pos else 0
    pz = float(m_pos.group(3).strip()) if m_pos else 0
    ox = float(m_ori.group(1).strip()) if m_ori else 0
    oy = float(m_ori.group(2).strip()) if m_ori else 0
    oz = float(m_ori.group(3).strip()) if m_ori else 0
    ow = float(m_ori.group(4).strip()) if m_ori else 1

    yaw = math.atan2(2*(ow*oz + ox*oy), 1 - 2*(oy*oy + oz*oz))
    print(f"  {name:12s}  <pose>{px:.3f} {py:.3f} {pz:.3f} 0 0 {yaw:.4f}</pose>")
