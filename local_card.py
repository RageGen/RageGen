"""Render a configurable Neofetch-style card with Pillow, entirely locally."""
import re, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from github_data import values
ROOT = Path(__file__).resolve().parent

def expand(text, data):
    def replacement(match):
        if match[1] not in data:
            raise ValueError(f'Unsupported placeholder: {match[0]}')
        return data[match[1]]
    return re.sub(r'\{\{(\w+)\}\}', replacement, str(text))

def dark(color, fallback):
    return color.split(',')[-1].strip() if color else fallback

def ascii_rows(config):
    path = config.get('image_file', 'assets/smiley.png')
    if '://' in path:
        raise ValueError('image_file must be local; remote images are not fetched.')
    with Image.open(ROOT/path) as source:
        rgba = source.convert('RGBA')
        bg = Image.new('RGBA', rgba.size, 'white'); bg.alpha_composite(rgba)
        gray = bg.convert('L')
        scale = min(38/gray.width, 50/gray.height)*config.get('imageScale',1)
        if scale <= 0:
            return [' '*38]*25
        size = (max(1,round(gray.width*scale)),max(1,round(gray.height*scale/2)))
        gray = gray.resize(size,Image.Resampling.LANCZOS)
        grid = Image.new('L',(38,25),255)
        grid.paste(gray,((38-size[0])//2+int(config.get('imageOffsetX',0)),(25-size[1])//2+int(config.get('imageOffsetY',0))))
    if config.get('ascii_mode')=='silhouette':
        # Average mirrored samples before thresholding: stable, symmetric edges.
        threshold=config.get('ascii_threshold',128)
        symmetric=config.get('ascii_symmetric',False)
        rows=[]
        for y in range(25):
            row=''
            for x in range(38):
                value=grid.getpixel((x,y))
                if symmetric:
                    value=(value+grid.getpixel((37-x,y)))/2
                row += '#' if value<threshold else ' '
            rows.append(row)
        return rows
    chars = ' .:-=+*#%@'
    return [''.join(chars[round((255-grid.getpixel((x,y)))/255*9)] for x in range(38)) for y in range(25)]

def render(snapshot,config):
    data = values(snapshot)
    font = ImageFont.truetype(str(ROOT/'assets/fonts/NotoSansMono.ttf'),20)
    cw = font.getlength('M'); line_height=28; right_x=250; max_chars=58
    rows=[]
    def add(text,color='#c9d1d9'):
        for line in textwrap.wrap(str(text),width=max_chars,replace_whitespace=True,drop_whitespace=True) or ['']:
            rows.append((line,color))
    def section_rows(section, limit):
        result=[]
        if section.get('title'):
            title=expand(section['title'],data)
            color=dark(section.get('titleColor',{}).get('text'),'#c9d1d9')
            result.extend((line+' '+ '─'*max(0,limit-len(line)-1),color) for line in textwrap.wrap(title,width=limit))
        for field in section['fields']:
            key=expand(field['key'],data)+': '
            value=expand(field['value'],data)
            key_color=dark(field.get('keyColor'),'#ffa657')
            value_color=dark(field.get('valueColor'),'#a5d6ff')
            wrapped=textwrap.wrap(value,width=max(1,limit-len(key)-3)) or ['—']
            result.append(((key,wrapped[0],limit),(key_color,value_color)))
            result.extend(('  '+line,value_color) for line in wrapped[1:])
        return result

    for section in config.get('sections',[]):
        if 'columns' in section:
            if len(section['columns'])!=2:
                raise ValueError('Column groups must contain exactly two sections.')
            column_width=(max_chars-4)//2
            columns=[section_rows(column,column_width) for column in section['columns']]
            for index in range(max(map(len,columns))):
                cells=[(column[index],j*(column_width+4)*cw) for j,column in enumerate(columns) if index<len(column)]
                rows.append(({'cells':cells},None))
        else:
            rows.extend(section_rows(section,max_chars))
        add('')
    stats=config.get('stats',{})
    if stats.get('enabled',True):
        title=stats.get('title','- GitHub Stats')
        add(title+' '+ '─'*max(0,max_chars-len(title)-1),dark(stats.get('titleColor',{}).get('text'),'#c9d1d9'))
        for row in stats.get('rows',[]):
            if row=='loc':
                rows.append(({'loc':data},None))
            elif isinstance(row,dict):
                cells=[]
                for j,side in enumerate(('left','right')):
                    if side in row:
                        field=dict(row[side])
                        field.setdefault('keyColor','#39e7ff')
                        field.setdefault('valueColor',stats.get('valueColor','#ffe24a'))
                        entries=section_rows({'fields':[field]},27)
                        cells.append((entries,j*31*cw))
                for index in range(max(len(entries) for entries,_ in cells)):
                    rows.append(({'cells':[(entries[index],offset) for entries,offset in cells if index<len(entries)]},None))
            else:
                raise ValueError('Unsupported statistics row')
    width=985;height=max(530,len(rows)*line_height+40)
    card=Image.new('RGBA',(width,height),(0,0,0,0));draw=ImageDraw.Draw(card)
    draw.rounded_rectangle((0,0,width-1,height-1),radius=15,fill=dark(config.get('backgroundColor'),'#161b22'))
    portrait=ascii_rows(config)
    portrait_font=ImageFont.truetype(str(ROOT/'assets/fonts/NotoSansMono.ttf'),10)
    for i,line in enumerate(portrait):
        draw.text((12,(height-25*14)//2+i*14),line,font=portrait_font,fill=dark(config.get('imageColor'),'#c9d1d9'))
    def draw_cell(xy,text,color):
        if isinstance(text,tuple):
            key,value,limit=text;key_color,val_color=color
            draw.text(xy,key,font=font,fill=key_color)
            value_x=xy[0]+limit*cw-font.getlength(value)
            dots=max(0,int((value_x-xy[0]-font.getlength(key))/cw)-1)
            draw.text((xy[0]+font.getlength(key),xy[1]),'.'*dots,font=font,fill='#61758a')
            draw.text((value_x,xy[1]),value,font=font,fill=val_color)
        else:
            draw.text(xy,text,font=font,fill=color)

    for i,(text,color) in enumerate(rows):
        xy=(right_x,18+i*line_height)
        if isinstance(text,dict) and 'loc' in text:
            d=text['loc']
            segments=[('Lines of Code: ', '#39e7ff'),(d['loc']+' ( ', '#ffe24a'),(d['additions']+'++', '#80ff70'),(', ', '#c9d1d9'),(d['deletions']+'--', '#ff7b54'),(' )', '#c9d1d9')]
            total=sum(font.getlength(t) for t,_ in segments)
            dots=max(0,int((max_chars*cw-total)/cw))
            segments.insert(1,('.'*dots,'#61758a'))
            x,y=xy
            for t,c in segments:
                draw.text((x,y),t,font=font,fill=c);x+=font.getlength(t)
        elif isinstance(text,dict):
            for (cell_text,cell_color),offset in text['cells']:
                draw_cell((xy[0]+offset,xy[1]),cell_text,cell_color)
        else:
            draw_cell(xy,text,color)
    return card
