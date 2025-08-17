# Build serverless web application with Holoviz Panel
[Panel][1] is a Python library for building web applications, mainly serves as
a bridge between [Bokeh][2] and [HoloViews][3]. (If you don't use HoloViews
directly or indirectly, you may want to skip this topic and search for some
alternative libraries.)  
Panel runs on both CPython and Pyodide. For installation, please refer to the
[tutorial][4]. Beyond that, in Mahoraga we provide proxy for Panel/Bokeh
frontend assets, eliminating direct requests to upstream servers completely.
The following example is for Pyodide, but can be adapted to CPython as well.
!!! note

    Mahoraga serves on `http://127.0.0.1:3450` by default. Replace it with the
    actual URL exposed to your clients.

## Prerequisites
- A running Mahoraga server which we have set up in the previous [tutorial][4].
- [CORS][5] must be enabled.
## Simple slider panel
The following example is just a combination of the [Mahoraga][5], [Panel][6]
and [Pyodide][7] tutorials. The key point is the script `panel_support.py`
^[:octicons-link-external-16:][8]^ which replaces all the hard-coded
URLs in Panel with a runtime configurable prefix, i.e. the Mahoraga URL.
=== "Pyodide"

    ``` html hl_lines="6-10 27 31 37"
    <!doctype html>
    <html>
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script type="text/javascript" src="http://127.0.0.1:3450/pyodide/v0.28.1/full/pyodide.js"></script>
        <script type="text/javascript" src="http://127.0.0.1:3450/npm/@bokeh/bokehjs@3.6.3/build/js/bokeh.min.js"></script>
        <script type="text/javascript" src="http://127.0.0.1:3450/npm/@bokeh/bokehjs@3.6.3/build/js/bokeh-widgets.min.js"></script>
        <script type="text/javascript" src="http://127.0.0.1:3450/npm/@bokeh/bokehjs@3.6.3/build/js/bokeh-tables.min.js"></script>
        <script type="text/javascript" src="http://127.0.0.1:3450/npm/@holoviz/panel@{{ panel_version }}/dist/panel.min.js"></script>
      </head>
      <body>
        <div id="simple_app"></div>
        <script type="text/javascript">
          async function main() {
            let pyodide = await loadPyodide();
            await pyodide.loadPackage("micropip");
            pyodide.runPython(`
                import micropip
                class _Transaction(micropip.transaction.Transaction):
                    def __post_init__(self):
                        super().__post_init__()
                        self.search_pyodide_lock_first = True
                micropip.package_manager.Transaction = _Transaction
            `);
            const micropip = pyodide.pyimport("micropip");
            micropip.set_index_urls("http://127.0.0.1:3450/pypi/simple/{package_name}/?micropip=1");
            await micropip.install(["panel =={{ panel_version }}"]);
            await pyodide.runPythonAsync(`
                from pyodide.http import pyfetch
                response = await pyfetch("http://127.0.0.1:3450/static/panel_support.py")
                with open("panel_support.py", "wb") as f:
                    f.write(await response.bytes())
            `);
            pyodide.runPython(`
                import panel_support
                panel_support.monkey_patch("http://127.0.0.1:3450/")
                import panel as pn
                pn.extension(sizing_mode="stretch_width")
                slider = pn.widgets.FloatSlider(start=0, end=10, name="Amplitude")
                def callback(new):
                    return f"Amplitude is: {new}"
                pn.Row(slider, pn.bind(callback, slider)).servable(target="simple_app")
            `);
          }
          main();
        </script>
      </body>
    </html>
    ```

=== "PyScript"

    ``` html hl_lines="6-11 16 25 29 34"
    <!doctype html>
    <html>
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script type="text/javascript" src="http://127.0.0.1:3450/npm/@bokeh/bokehjs@3.6.3/build/js/bokeh.min.js"></script>
        <script type="text/javascript" src="http://127.0.0.1:3450/npm/@bokeh/bokehjs@3.6.3/build/js/bokeh-widgets.min.js"></script>
        <script type="text/javascript" src="http://127.0.0.1:3450/npm/@bokeh/bokehjs@3.6.3/build/js/bokeh-tables.min.js"></script>
        <script type="text/javascript" src="http://127.0.0.1:3450/npm/@holoviz/panel@{{ panel_version }}/dist/panel.min.js"></script>
        <script type="module" src="http://127.0.0.1:3450/npm/@pyscript/core@0/dist/core.js"></script>
        <link rel="stylesheet" href="http://127.0.0.1:3450/npm/@pyscript/core@0/dist/core.css">
      </head>
      <body>
        <div id="simple_app"></div>
        <script type="py" config='{
          "interpreter": "http://127.0.0.1:3450/pyodide/v0.28.1/full/pyodide.mjs",
          "packages": ["bokeh"]
        }'>
            import micropip
            class _Transaction(micropip.transaction.Transaction):
                def __post_init__(self):
                    super().__post_init__()
                    self.search_pyodide_lock_first = True
            micropip.package_manager.Transaction = _Transaction
            micropip.set_index_urls("http://127.0.0.1:3450/pypi/simple/{package_name}/?micropip=1")
            await micropip.install(["panel =={{ panel_version }}"])

            from pyodide.http import pyfetch
            response = await pyfetch("http://127.0.0.1:3450/static/panel_support.py")
            with open("panel_support.py", "wb") as f:
                f.write(await response.bytes())

            import panel_support
            panel_support.monkey_patch("http://127.0.0.1:3450/")
            import panel as pn
            pn.extension(sizing_mode="stretch_width")
            slider = pn.widgets.FloatSlider(start=0, end=10, name="Amplitude")
            def callback(new):
                return f"Amplitude is: {new}"
            pn.Row(slider, pn.bind(callback, slider)).servable(target="simple_app")
        </script>
      </body>
    </html>
    ```

[1]: https://panel.holoviz.org/
[2]: https://bokeh.org/
[3]: https://holoviews.org/
[4]: ../tutorial.md
[5]: ../tutorial.md#pyodide
[6]: https://panel.holoviz.org/how_to/wasm/standalone.html
[7]: https://pyodide.org/en/stable/usage/loading-custom-python-code.html#loading-then-importing-python-code
[8]: https://github.com/hingebase/mahoraga/blob/v{{ mahoraga_version }}/src/mahoraga/_static/panel_support.py
