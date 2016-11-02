from Tools.Profile import profile
profile("LOAD:ElementTree")
import xml.etree.cElementTree
from os import path

profile("LOAD:enigma_skin")
from enigma import eSize, ePoint, gFont, eWindow, eLabel, ePixmap, eWindowStyleManager, \
	addFont, gRGB, eWindowStyleSkinned
from Components.config import ConfigSubsection, ConfigText, ConfigInteger, config
from Components.Converter.Converter import Converter
from Components.Sources.Source import Source, ObsoleteSource
from Tools.Directories import resolveFilename, SCOPE_SKIN, SCOPE_SKIN_IMAGE, SCOPE_FONTS, SCOPE_CURRENT_SKIN, SCOPE_CONFIG, fileExists
from Tools.Import import my_import
from Tools.LoadPixmap import LoadPixmap

colorNames = dict()

fonts = {
	"Body": ("Regular", 18, 22, 16),
	"ChoiceList": ("Regular", 20, 25, 18),
}

def dump(x, i=0):
	print " " * i + str(x)
	try:
		for n in x.childNodes:
			dump(n, i + 1)
	except:
		None

class SkinError(Exception):
	def __init__(self, message):
		self.msg = message

	def __str__(self):
		return "{%s}: %s" % (config.skin.primary_skin.value, self.msg)

dom_skins = [ ]

def loadSkin(name, scope = SCOPE_SKIN):
	# read the skin
	filename = resolveFilename(scope, name)
	mpath = path.dirname(filename) + "/"
	dom_skins.append((mpath, xml.etree.cElementTree.parse(filename).getroot()))

# we do our best to always select the "right" value
# skins are loaded in order of priority: skin with
# highest priority is loaded last, usually the user-provided
# skin.

# currently, loadSingleSkinData (colors, bordersets etc.)
# are applied one-after-each, in order of ascending priority.
# the dom_skin will keep all screens in descending priority,
# so the first screen found will be used.

# example: loadSkin("nemesis_greenline/skin.xml")
config.skin = ConfigSubsection()
config.skin.primary_skin = ConfigText(default = "skin.xml")
config.skin.xres = ConfigInteger(default = 0)

profile("LoadSkin")
try:
	loadSkin('skin_user.xml', SCOPE_CONFIG)
except (SkinError, IOError, AssertionError), err:
	print "not loading user skin: ", err

try:
	loadSkin(config.skin.primary_skin.value)
except (SkinError, IOError, AssertionError), err:
	print "SKIN ERROR:", err
	print "defaulting to standard skin..."
	config.skin.primary_skin.value = 'skin.xml'
	loadSkin('skin.xml')

profile("LoadSkinDefault")
loadSkin('skin_default.xml')
profile("LoadSkinDefaultDone")

def parseCoordinate(str, e, size = 0):
	str = str.strip()
	if str == "center":
		val = (e - size)/2
	else:
		sl = len(str)
		l = 1

		if str[0] is 'e':
			val = e
		elif str[0] is 'c':
			val = e/2
		else:
			val = 0;
			l = 0

		if sl - l > 0:
			if str[sl-1] is '%':
				val += e * int(str[l:sl-1]) / 100
			else:
				val += int(str[l:sl])
	if val < 0:
		val = 0
	return val

def getParentSize(object, desktop):
	size = eSize()
	if object:
		parent = object.getParent()
		# For some widgets (e.g. ScrollLabel) the skin attributes are applied to
		# a child widget, instead of to the widget itself. In that case, the parent
		# we have here is not the real parent, but it is the main widget.
		# We have to go one level higher to get the actual parent.
		# We can detect this because the 'parent' will not have a size yet
		# (the main widget's size will be calculated internally, as soon as the child
		# widget has parsed the skin attributes)
		if parent and parent.size().isEmpty():
			parent = parent.getParent()
		if parent:
			size = parent.size()
		elif desktop:
			#widget has no parent, use desktop size instead for relative coordinates
			size = desktop.size()
	return size

def parsePosition(str, scale, object = None, desktop = None, size = None):
	x, y = str.split(',')
	parentsize = eSize()
	if object and (x[0] in ['c', 'e'] or y[0] in ['c', 'e']):
		parentsize = getParentSize(object, desktop)
	xval = parseCoordinate(x, parentsize.width(), size and size.width())
	yval = parseCoordinate(y, parentsize.height(), size and size.height())
	return ePoint(xval * scale[0][0] / scale[0][1], yval * scale[1][0] / scale[1][1])

def parseSize(str, scale, object = None, desktop = None):
	x, y = str.split(',')
	parentsize = eSize()
	if object and (x[0] in ['c', 'e'] or y[0] in ['c', 'e']):
		parentsize = getParentSize(object, desktop)
	xval = parseCoordinate(x, parentsize.width())
	yval = parseCoordinate(y, parentsize.height())
	return eSize(xval * scale[0][0] / scale[0][1], yval * scale[1][0] / scale[1][1])

def parseFont(str, scale):
	name, size = str.split(';')
	return gFont(name, int(size) * scale[0][0] / scale[0][1])

def parseColor(str):
	if str[0] != '#':
		try:
			return colorNames[str]
		except:
			raise SkinError("color '%s' must be #aarrggbb or valid named color" % (str))
	return gRGB(int(str[1:], 0x10))

def collectAttributes(skinAttributes, node, skin_path_prefix=None, ignore=[]):
	# walk all attributes
	for a in node.items():
		#print a
		attrib = a[0]
		value = a[1]

		if attrib in ("pixmap", "pointer", "seek_pointer", "backgroundPixmap", "selectionPixmap"):
			value = resolveFilename(SCOPE_SKIN_IMAGE, value, path_prefix=skin_path_prefix)

		if attrib not in ignore:
			skinAttributes.append((attrib, value.encode("utf-8")))

def loadPixmap(path, desktop):
	cached = False
	option = path.find("#")
	if option != -1:
		options = path[option+1:].split(',')
		path = path[:option]
		cached = "cached" in options
	ptr = LoadPixmap(path, desktop, cached)
	if ptr is None:
		raise SkinError("pixmap file %s not found!" % (path))
	return ptr

def applySingleAttribute(guiObject, desktop, attrib, value, scale = ((1,1),(1,1))):
	# and set attributes
	try:
		if attrib == 'position':
			guiObject.move(parsePosition(value, scale, guiObject, desktop, guiObject.csize()))
		elif attrib == 'size':
			guiObject.resize(parseSize(value, scale, guiObject, desktop))
		elif attrib == 'animationPaused':
			pass
		elif attrib == 'animationMode':
			guiObject.setAnimationMode(
				{ "disable": 0x00,
					"off": 0x00,
					"offshow": 0x10,
					"offhide": 0x01,
					"onshow": 0x01,
					"onhide": 0x10,
				}[value])
		elif attrib == 'title':
			guiObject.setTitle(_(value))
		elif attrib == 'text':
			guiObject.setText(_(value))
		elif attrib == 'font':
			guiObject.setFont(parseFont(value, scale))
		elif attrib == 'zPosition':
			guiObject.setZPosition(int(value))
		elif attrib == 'itemHeight':
			guiObject.setItemHeight(int(value))
		elif attrib in ("pixmap", "backgroundPixmap", "selectionPixmap"):
			ptr = loadPixmap(value, desktop) # this should already have been filename-resolved.
			if attrib == "pixmap":
				guiObject.setPixmap(ptr)
			elif attrib == "backgroundPixmap":
				guiObject.setBackgroundPicture(ptr)
			elif attrib == "selectionPixmap":
				guiObject.setSelectionPicture(ptr)
			# guiObject.setPixmapFromFile(value)
		elif attrib == "alphatest": # used by ePixmap
			guiObject.setAlphatest(
				{ "on": 1,
				  "off": 0,
				  "blend": 2,
				}[value])
		elif attrib == "scale":
			guiObject.setScale(1)
		elif attrib == "orientation": # used by eSlider
			try:
				guiObject.setOrientation(*
					{ "orVertical": (guiObject.orVertical, False),
						"orTopToBottom": (guiObject.orVertical, False),
						"orBottomToTop": (guiObject.orVertical, True),
						"orHorizontal": (guiObject.orHorizontal, False),
						"orLeftToRight": (guiObject.orHorizontal, False),
						"orRightToLeft": (guiObject.orHorizontal, True),
					}[value])
			except KeyError:
				print "oprientation must be either orVertical or orHorizontal!"
		elif attrib == "valign":
			try:
				guiObject.setVAlign(
					{ "top": guiObject.alignTop,
						"center": guiObject.alignCenter,
						"bottom": guiObject.alignBottom
					}[value])
			except KeyError:
				print "valign must be either top, center or bottom!"
		elif attrib == "halign":
			try:
				guiObject.setHAlign(
					{ "left": guiObject.alignLeft,
						"center": guiObject.alignCenter,
						"right": guiObject.alignRight,
						"block": guiObject.alignBlock
					}[value])
			except KeyError:
				print "halign must be either left, center, right or block!"
		elif attrib == "flags":
			flags = value.split(',')
			for f in flags:
				try:
					fv = eWindow.__dict__[f]
					guiObject.setFlag(fv)
				except KeyError:
					print "illegal flag %s!" % f
		elif attrib == "backgroundColor":
			guiObject.setBackgroundColor(parseColor(value))
		elif attrib == "backgroundColorSelected":
			guiObject.setBackgroundColorSelected(parseColor(value))
		elif attrib == "foregroundColor":
			guiObject.setForegroundColor(parseColor(value))
		elif attrib == "foregroundColorSelected":
			guiObject.setForegroundColorSelected(parseColor(value))
		elif attrib == "shadowColor":
			guiObject.setShadowColor(parseColor(value))
		elif attrib == "selectionDisabled":
			guiObject.setSelectionEnable(0)
		elif attrib == "transparent":
			guiObject.setTransparent(int(value))
		elif attrib == "borderColor":
			guiObject.setBorderColor(parseColor(value))
		elif attrib == "borderWidth":
			guiObject.setBorderWidth(int(value))
		elif attrib == "scrollbarMode":
			guiObject.setScrollbarMode(
				{ "showOnDemand": guiObject.showOnDemand,
					"showAlways": guiObject.showAlways,
					"showNever": guiObject.showNever
				}[value])
		elif attrib == "enableWrapAround":
			guiObject.setWrapAround(True)
		elif attrib == "pointer" or attrib == "seek_pointer":
			(name, pos) = value.split(':')
			pos = parsePosition(pos, scale)
			ptr = loadPixmap(name, desktop)
			guiObject.setPointer({"pointer": 0, "seek_pointer": 1}[attrib], ptr, pos)
		elif attrib == 'shadowOffset':
			guiObject.setShadowOffset(parsePosition(value, scale))
		elif attrib == 'noWrap':
			guiObject.setNoWrap(1)
		elif attrib == 'id':
			pass
		else:
			raise SkinError("unsupported attribute " + attrib + "=" + value)
	except int:
# AttributeError:
		print "widget %s (%s) doesn't support attribute %s!" % ("", guiObject.__class__.__name__, attrib)

def applyAllAttributes(guiObject, desktop, attributes, scale):
	for (attrib, value) in attributes:
		applySingleAttribute(guiObject, desktop, attrib, value, scale)

def loadSingleSkinData(desktop, skin, path_prefix):
	"""loads skin data like colors, windowstyle etc."""
	assert skin.tag == "skin", "root element in skin must be 'skin'!"

	#print "***SKIN: ", path_prefix

	for c in skin.findall("output"):
		id = c.attrib.get('id')
		if id:
			id = int(id)
		else:
			id = 0
		if id == 0: # framebuffer
			for res in c.findall("resolution"):
				get_attr = res.attrib.get
				xres = get_attr("xres")
				if xres:
					xres = int(xres)
				else:
					xres = 720
				yres = get_attr("yres")
				if yres:
					yres = int(yres)
				else:
					yres = 576
				bpp = get_attr("bpp")
				if bpp:
					bpp = int(bpp)
				else:
					bpp = 32
				#print "Resolution:", xres,yres,bpp
				config.skin.xres.value = xres
				from enigma import gMainDC
				gMainDC.getInstance().setResolution(xres, yres)
				desktop.resize(eSize(xres, yres))
				if bpp != 32:
					# load palette (not yet implemented)
					pass

	for c in skin.findall("colors"):
		for color in c.findall("color"):
			get_attr = color.attrib.get
			name = get_attr("name")
			color = get_attr("value")
			if name and color:
				colorNames[name] = parseColor(color)
				#print "Color:", name, color
			else:
				raise SkinError("need color and name, got %s %s" % (name, color))

	for c in skin.findall("fonts"):
		for font in c.findall("font"):
			get_attr = font.attrib.get
			filename = get_attr("filename", "<NONAME>")
			name = get_attr("name", "Regular")
			scale = get_attr("scale")
			if scale:
				scale = int(scale)
			else:
				scale = 100
			is_replacement = get_attr("replacement") and True or False
			resolved_font = resolveFilename(SCOPE_FONTS, filename, path_prefix=path_prefix)
			if not fileExists(resolved_font): #when font is not available look at current skin path
				skin_path = resolveFilename(SCOPE_CURRENT_SKIN, filename)
				if fileExists(skin_path):
					resolved_font = skin_path
			addFont(resolved_font, name, scale, is_replacement)
			#print "Font: ", resolved_font, name, scale, is_replacement
		for alias in c.findall("alias"):
		        get = alias.attrib.get
		        try:
				name = get("name")
				font = get("font")
				size = int(get("size"))
				height = int(get("height", size)) # to be calculated some day
				width = int(get("width", size))
				global fonts
				fonts[name] = (font, size, height, width)
			except Exception, ex:
				print "[SKIN] bad font alias", ex

	for c in skin.findall("subtitles"):
		from enigma import eWidget, eSubtitleWidget
		scale = ((1,1),(1,1))
		for substyle in c.findall("sub"):
			get_attr = substyle.attrib.get
			font = parseFont(get_attr("font"), scale)
			col = get_attr("foregroundColor")
			if col:
				foregroundColor = parseColor(col)
				haveColor = 1
			else:
				foregroundColor = gRGB(0xFFFFFF)
				haveColor = 0
			col = get_attr("shadowColor")
			if col:
				shadowColor = parseColor(col)
			else:
				shadowColor = gRGB(0)
			shadowOffset = parsePosition(get_attr("shadowOffset"), scale)
			face = eSubtitleWidget.__dict__[get_attr("name")]
			eSubtitleWidget.setFontStyle(face, font, haveColor, foregroundColor, shadowColor, shadowOffset)

	for windowstyle in skin.findall("windowstyle"):
		style = eWindowStyleSkinned()
		id = windowstyle.attrib.get("id")
		if id:
			id = int(id)
		else:
			id = 0
		#print "windowstyle:", id

		# defaults
		font = gFont("Regular", 20)
		offset = eSize(20, 5)

		for title in windowstyle.findall("title"):
			get_attr = title.attrib.get
			offset = parseSize(get_attr("offset"), ((1,1),(1,1)))
			font = parseFont(get_attr("font"), ((1,1),(1,1)))

		style.setTitleFont(font);
		style.setTitleOffset(offset)
		#print "  ", font, offset

		for borderset in windowstyle.findall("borderset"):
			bsName = str(borderset.attrib.get("name"))
			for pixmap in borderset.findall("pixmap"):
				get_attr = pixmap.attrib.get
				bpName = get_attr("pos")
				filename = get_attr("filename")
				if filename and bpName:
					png = loadPixmap(resolveFilename(SCOPE_SKIN_IMAGE, filename, path_prefix=path_prefix), desktop)
					style.setPixmap(eWindowStyleSkinned.__dict__[bsName], eWindowStyleSkinned.__dict__[bpName], png)
				#print "  borderset:", bpName, filename

		for color in windowstyle.findall("color"):
			get_attr = color.attrib.get
			colorType = get_attr("name")
			color = parseColor(get_attr("color"))
			try:
				style.setColor(eWindowStyleSkinned.__dict__["col" + colorType], color)
			except:
				raise SkinError("Unknown color %s" % (colorType))
				#pass

			#print "  color:", type, color

		x = eWindowStyleManager.getInstance()
		x.setStyle(id, style)

def loadSkinData(desktop):
	skins = dom_skins[:]
	skins.reverse()
	for (path, dom_skin) in skins:
		loadSingleSkinData(desktop, dom_skin, path)

def lookupScreen(name, style_id):
	for (path, skin) in dom_skins:
		# first, find the corresponding screen element
		for x in skin.findall("screen"):
			if x.attrib.get('name', '') == name:
				screen_style_id = x.attrib.get('id', '-1')
				if screen_style_id == '-1' and name.find('ummary') > 0:
					screen_style_id = '1'
				if (style_id != 2 and int(screen_style_id) == -1) or int(screen_style_id) == style_id:
					return x, path
	return None, None

class additionalWidget:
	pass

def readSkin(screen, skin, names, desktop):
	if not isinstance(names, list):
		names = [names]

	name = "<embedded-in-'%s'>" % screen.__class__.__name__

	style_id = desktop.getStyleID();

	# try all skins, first existing one have priority
	for n in names:
		myscreen, path = lookupScreen(n, style_id)
		if myscreen is not None:
			# use this name for debug output
			name = n
			break

	# otherwise try embedded skin
	if myscreen is None:
		myscreen = getattr(screen, "parsedSkin", None)

	# try uncompiled embedded skin
	if myscreen is None and getattr(screen, "skin", None):
		print "Looking for embedded skin"
		skin_tuple = screen.skin
		if not isinstance(skin_tuple, tuple):
			skin_tuple = (skin_tuple,)
		for sskin in skin_tuple:
			parsedSkin = xml.etree.cElementTree.fromstring(sskin)
			screen_style_id = parsedSkin.attrib.get('id', '-1')
			if (style_id != 2 and int(screen_style_id) == -1) or int(screen_style_id) == style_id:
				myscreen = screen.parsedSkin = parsedSkin
				break

	#assert myscreen is not None, "no skin for screen '" + repr(names) + "' found!"
	if myscreen is None:
		print "No skin to read..."
		emptySkin = "<screen></screen>"
		myscreen = screen.parsedSkin = xml.etree.cElementTree.fromstring(emptySkin)

	screen.skinAttributes = [ ]

	skin_path_prefix = getattr(screen, "skin_path", path)

	collectAttributes(screen.skinAttributes, myscreen, skin_path_prefix, ignore=["name"])

	screen.additionalWidgets = [ ]
	screen.renderer = [ ]

	visited_components = set()

	# now walk all widgets
	for widget in myscreen.findall("widget"):
		get_attr = widget.attrib.get
		# ok, we either have 1:1-mapped widgets ('old style'), or 1:n-mapped
		# widgets (source->renderer).

		wname = get_attr('name')
		wsource = get_attr('source')

		if wname is None and wsource is None:
			print "widget has no name and no source!"
			continue

		if wname:
			#print "Widget name=", wname
			visited_components.add(wname)

			# get corresponding 'gui' object
			try:
				attributes = screen[wname].skinAttributes = [ ]
			except:
				raise SkinError("component with name '" + wname + "' was not found in skin of screen '" + name + "'!")
				#print "WARNING: component with name '" + wname + "' was not found in skin of screen '" + name + "'!"

#			assert screen[wname] is not Source

			# and collect attributes for this
			collectAttributes(attributes, widget, skin_path_prefix, ignore=['name'])
		elif wsource:
			# get corresponding source
			#print "Widget source=", wsource

			while True: # until we found a non-obsolete source

				# parse our current "wsource", which might specifiy a "related screen" before the dot,
				# for example to reference a parent, global or session-global screen.
				scr = screen

				# resolve all path components
				path = wsource.split('.')
				while len(path) > 1:
					scr = screen.getRelatedScreen(path[0])
					if scr is None:
						#print wsource
						#print name
						raise SkinError("specified related screen '" + wsource + "' was not found in screen '" + name + "'!")
					path = path[1:]

				# resolve the source.
				source = scr.get(path[0])
				if isinstance(source, ObsoleteSource):
					# however, if we found an "obsolete source", issue warning, and resolve the real source.
					print "WARNING: SKIN '%s' USES OBSOLETE SOURCE '%s', USE '%s' INSTEAD!" % (name, wsource, source.new_source)
					print "OBSOLETE SOURCE WILL BE REMOVED %s, PLEASE UPDATE!" % (source.removal_date)
					if source.description:
						print source.description

					wsource = source.new_source
				else:
					# otherwise, use that source.
					break

			if source is None:
				raise SkinError("source '" + wsource + "' was not found in screen '" + name + "'!")

			wrender = get_attr('render')

			if not wrender:
				raise SkinError("you must define a renderer with render= for source '%s'" % (wsource))

			for converter in widget.findall("convert"):
				ctype = converter.get('type')
				assert ctype, "'convert'-tag needs a 'type'-attribute"
				#print "Converter:", ctype
				try:
					parms = converter.text.strip()
				except:
					parms = ""
				#print "Params:", parms
				converter_class = my_import('.'.join(("Components", "Converter", ctype))).__dict__.get(ctype)

				c = None

				for i in source.downstream_elements:
					if isinstance(i, converter_class) and i.converter_arguments == parms:
						c = i

				if c is None:
					print "allocating new converter!"
					c = converter_class(parms)
					c.connect(source)
				else:
					print "reused converter!"

				source = c

			renderer_class = my_import('.'.join(("Components", "Renderer", wrender))).__dict__.get(wrender)

			renderer = renderer_class() # instantiate renderer

			renderer.connect(source) # connect to source
			attributes = renderer.skinAttributes = [ ]
			collectAttributes(attributes, widget, skin_path_prefix, ignore=['render', 'source'])

			screen.renderer.append(renderer)

	from Components.GUIComponent import GUIComponent
	nonvisited_components = [x for x in set(screen.keys()) - visited_components if isinstance(x, GUIComponent)]
	assert not nonvisited_components, "the following components in %s don't have a skin entry: %s" % (name, ', '.join(nonvisited_components))

	# now walk additional objects
	for widget in myscreen.getchildren():
		w_tag = widget.tag

		if w_tag == "widget":
			continue

		if w_tag == "applet":
			try:
				codeText = widget.text.strip()
			except:
				codeText = ""

			#print "Found code:"
			#print codeText
			widgetType = widget.attrib.get('type')

			code = compile(codeText, "skin applet", "exec")

			if widgetType == "onLayoutFinish":
				screen.onLayoutFinish.append(code)
				#print "onLayoutFinish = ", codeText
			else:
				raise SkinError("applet type '%s' unknown!" % widgetType)
				#print "applet type '%s' unknown!" % type

			continue

		w = additionalWidget()

		if w_tag == "eLabel":
			w.widget = eLabel
		elif w_tag == "ePixmap":
			w.widget = ePixmap
		else:
			raise SkinError("unsupported stuff : %s" % w_tag)
			#print "unsupported stuff : %s" % widget.tag

		w.skinAttributes = [ ]
		collectAttributes(w.skinAttributes, widget, skin_path_prefix, ignore=['name'])

		# applyAttributes(guiObject, widget, desktop)
		# guiObject.thisown = 0
		screen.additionalWidgets.append(w)
