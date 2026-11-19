#!/usr/bin/env python3
"""Render locally with cached assets; fetch public data only from api.github.com."""
from pathlib import Path
import argparse, json, math, random, sys, urllib.error
from PIL import Image, ImageDraw
from github_data import collect
from local_card import render
ROOT = Path(__file__).resolve().parent

def load_animation(path, width):
    frames, ends, elapsed = [], [], 0
    with Image.open(path) as image:
        for i in range(getattr(image, 'n_frames', 1)):
            image.seek(i)
            frame = image.convert('RGBA')
            frame = frame.resize((width, max(1, round(frame.height*width/frame.width))), Image.Resampling.NEAREST)
            elapsed += max(20, image.info.get('duration', 100))
            frames.append(frame); ends.append(elapsed)
    return frames, ends, elapsed

def frame_at(animation, time):
    frames, ends, total = animation
    phase = time % total
    return next(frame for frame, end in zip(frames, ends) if phase < end)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--offline',action='store_true',help='Render using cached GitHub JSON; no network')
    parser.add_argument('--require-fresh',action='store_true',help='Fail rather than reuse cached GitHub data')
    args=parser.parse_args()
    if args.offline and args.require_fresh:
        parser.error('--offline and --require-fresh cannot be combined')
    config=json.loads((ROOT/'layout.json').read_text())
    local=json.loads((ROOT/'neofetch.json').read_text())
    cache=ROOT/'assets/github-profile.json'
    fresh=False
    if args.offline:
        if not cache.exists():
            raise ValueError('No GitHub data cache. Run once online to create it.')
        snapshot=json.loads(cache.read_text())
    else:
        try:
            snapshot=collect(config['username']);fresh=True
        except (urllib.error.URLError, OSError) as exc:
            if args.require_fresh or not cache.exists():
                raise
            print(f'Warning: GitHub refresh failed ({exc}); using cached GitHub data.',file=sys.stderr)
            snapshot=json.loads(cache.read_text())
    if snapshot['username'].lower()!=config['username'].lower():
        raise ValueError('Cache belongs to another username; refresh online.')
    print(f'GitHub data captured: {snapshot["fetched_at"]}',flush=True)
    card=render(snapshot,local)
    w, h = config['canvas']
    card_w = config['card_width']
    # Keep taller cards inside the ring as sections are added.
    scale = min(card_w/card.width, config.get('card_max_height', h*0.48)/card.height)
    card = card.resize((round(card.width*scale), round(card.height*scale)), Image.Resampling.LANCZOS)
    center = (w//2, h//2)
    card_xy = (center[0]-card.width//2, center[1]-card.height//2)
    base = Image.new('RGBA', (w,h), config['background'])
    if config.get('background_file'):
        base=Image.open(ROOT/config['background_file']).convert('RGBA').resize((w,h))
    draw = ImageDraw.Draw(base)
    rng = random.Random(config['seed'])
    for _ in range(0 if config.get('background_file') else 180):
        x,y = rng.randrange(w),rng.randrange(h)
        draw.rectangle((x,y,x+1,y+1), fill=rng.choice(['#384361','#7186a0','#ad9eb9']))
    sprites = []
    for item in config['elements']:
        anim = load_animation(ROOT/'assets'/item['file'], item['width'])
        a = math.radians(item.get('angle',0))
        x = item.get('x',center[0] + config['radius'][0]*math.cos(a) + item.get('dx',0))
        y = item.get('y',center[1] + config['radius'][1]*math.sin(a) + item.get('dy',0))
        fw,fh = anim[0][0].size
        bounds = (round(x-fw/2), round(y-fh/2), round(x+fw/2), round(y+fh/2))
        if bounds[0]<0 or bounds[1]<0 or bounds[2]>w or bounds[3]>h:
            raise ValueError(f'Asset outside canvas: {item["file"]}')
        if bounds[0]<card_xy[0]+card.width and bounds[2]>card_xy[0] and bounds[1]<card_xy[1]+card.height and bounds[3]>card_xy[1]:
            raise ValueError(f'Asset overlaps card: {item["file"]}')
        sprites.append((anim, bounds[:2], item.get('phase_ms',rng.randrange(3000)),item.get('motion')))
    base.alpha_composite(card,card_xy)
    frames=[]
    step=round(1000/config['fps']/10)*10
    for t in range(0,config['duration_ms'],step):
        frame=base.copy()
        for anim,xy,phase,motion in sprites:
            sprite=frame_at(anim,t+phase)
            wave=math.sin(2*math.pi*(t+phase)/config['duration_ms'])
            if motion=='float':
                xy=(xy[0],xy[1]+round(3*wave))
            elif motion=='twinkle':
                sprite=sprite.copy()
                sprite.putalpha(sprite.getchannel('A').point(lambda v:round(v*(0.65+0.35*(wave+1)/2))))
            frame.alpha_composite(sprite,xy)
        frames.append(frame.convert('RGB'))
    # A shared palette keeps the terminal stable while decorations animate.
    sheet=Image.new('RGB',(w,h*min(8,len(frames))))
    for i in range(min(8,len(frames))):sheet.paste(frames[i*len(frames)//min(8,len(frames))],(0,h*i))
    palette=sheet.quantize(colors=256)
    indexed=[f.quantize(palette=palette,dither=Image.Dither.NONE) for f in frames]
    target=ROOT/'generated';target.mkdir(exist_ok=True)
    card.save(target/'card.png')
    gif=target/'profile.gif';temp=target/'profile.tmp.gif'
    indexed[0].save(temp,save_all=True,append_images=indexed[1:],duration=step,loop=0,optimize=False,disposal=1)
    temp.replace(gif)
    if fresh:
        cache.write_text(json.dumps(snapshot, indent=2)+"\n")
    print(f'Generated {gif.name}: {len(frames)} frames, {gif.stat().st_size:,} bytes; '+('fresh GitHub data; card rendered locally' if fresh else 'cached GitHub data; card rendered locally'))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,urllib.error.URLError) as exc:
        print(f'Error: {exc}',file=sys.stderr)
        raise SystemExit(1)
