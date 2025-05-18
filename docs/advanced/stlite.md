# Build serverless web application with Stlite
[Stlite][1] brings the [Streamlit][2] web application framework to Pyodide,
which is redistributable as a single HTML file, especially suitable for
prototype development and idea sharing. With a Mahoraga service in the same
Intranet, you and your audience won't have to take care of virtual environments,
dependencies, compilation and packaging. In this topic, we are going to serve
the Streamlit "Hello world" demo with Mahoraga.
!!! note

    Mahoraga serves on `http://127.0.0.1:3450` by default. Replace it with the
    actual URL exposed to your clients.
## Prerequisites
- A running Mahoraga server which we have set up in the previous [tutorial][3].
- A modern desktop or mobile web browser which meets the
  [requirement of Pyodide][4].
## Enable cross-origin resource sharing (CORS)
In your `mahoraga.toml` file, add a `"*"` to the list `cors.allow-origins`,
making it possible to open the Stlite HTML file directly from local disk
(no other web servers required).
## Write your HTML
Requests of the Stlite CSS and JavaScript files should be directed to Mahoraga,
as well as the `pyodideUrl` and `requirements` parameters of the Stlite `mount`
function:
```html title="hello.html"
<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />
    <title>Hello</title>
    <link rel="stylesheet" href="http://127.0.0.1:3450/npm/@stlite/browser@0/build/stlite.css" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module">
      import { mount } from "http://127.0.0.1:3450/npm/@stlite/browser@0/build/stlite.js";
      mount(
        {
          pyodideUrl: "http://127.0.0.1:3450/pyodide/v{{ pyodide_py_version }}/full/pyodide.js",
          requirements: [
            "http://127.0.0.1:3450/pypi/packages/py3/b/blinker/blinker-{{ blinker_version }}-py3-none-any.whl",
            "http://127.0.0.1:3450/pypi/packages/py3/t/tenacity/tenacity-{{ tenacity_version }}-py3-none-any.whl",
          ],
          entrypoint: "hello.py",
          files: {
            "hello.py": `import streamlit as st  # ...`,
            "agri.csv.gz": new Uint8Array([0x1f, 0x8b, /* ... */]),
          },
        },
        document.getElementById("root"),
      );
    </script>
  </body>
</html>
```
The Python code can be embedded into HTML directly as literal string:
```py title="hello.py"
import streamlit as st


async def intro():
    import streamlit as st

    st.write("# Welcome to Streamlit! 👋")
    st.sidebar.success("Select a demo above.")

    st.markdown(
        """
        Streamlit is an open-source app framework built specifically for
        Machine Learning and Data Science projects.

        **👈 Select a demo from the dropdown on the left** to see some examples
        of what Streamlit can do!

        ### Want to learn more?

        - Check out [streamlit.io](https://streamlit.io)
        - Jump into our [documentation](https://docs.streamlit.io)
        - Ask a question in our [community
          forums](https://discuss.streamlit.io)

        ### See more complex demos

        - Use a neural net to [analyze the Udacity Self-driving Car Image
          Dataset](https://github.com/streamlit/demo-self-driving)
        - Explore a [New York City rideshare dataset](https://github.com/streamlit/demo-uber-nyc-pickups)
    """
    )


async def plotting_demo():
    import asyncio

    import numpy as np
    import streamlit as st

    st.markdown(f"# {list(page_names_to_funcs.keys())[1]}")
    st.write(
        """
        This demo illustrates a combination of plotting and animation with
Streamlit. We're generating a bunch of random numbers in a loop for around
5 seconds. Enjoy!
"""
    )

    progress_bar = st.sidebar.progress(0)
    status_text = st.sidebar.empty()
    last_rows = np.random.randn(1, 1)
    chart = st.line_chart(last_rows)

    for i in range(1, 101):
        new_rows = last_rows[-1, :] + np.random.randn(5, 1).cumsum(axis=0)
        status_text.text("%i%% Complete" % i)
        chart.add_rows(new_rows)
        progress_bar.progress(i)
        last_rows = new_rows
        await asyncio.sleep(0.05)

    progress_bar.empty()

    # Streamlit widgets automatically run the script from top to bottom. Since
    # this button is not connected to any other logic, it just causes a plain
    # rerun.
    st.button("Re-run")


async def data_frame_demo():
    from urllib.error import URLError

    import altair as alt
    import pandas as pd
    import streamlit as st

    st.markdown(f"# {list(page_names_to_funcs.keys())[2]}")
    st.write(
        """
        This demo shows how to use \`st.write\` to visualize Pandas DataFrames.

(Data courtesy of the [UN Data Explorer](http://data.un.org/Explorer.aspx).)
"""
    )

    @st.cache_data
    def get_UN_data():
        # AWS_BUCKET_URL = "http://streamlit-demo-data.s3-us-west-2.amazonaws.com"
        # df = pd.read_csv(AWS_BUCKET_URL + "/agri.csv.gz")
        df = pd.read_csv("./agri.csv.gz")
        return df.set_index("Region")

    try:
        df = get_UN_data()
        countries = st.multiselect(
            "Choose countries", list(df.index), ["China", "United States of America"]
        )
        if not countries:
            st.error("Please select at least one country.")
        else:
            data = df.loc[countries]
            data /= 1000000.0
            st.write("### Gross Agricultural Production ($B)", data.sort_index())

            data = data.T.reset_index()
            data = pd.melt(data, id_vars=["index"]).rename(
                columns={"index": "year", "value": "Gross Agricultural Product ($B)"}
            )
            chart = (
                alt.Chart(data)
                .mark_area(opacity=0.3)
                .encode(
                    x="year:T",
                    y=alt.Y("Gross Agricultural Product ($B):Q", stack=None),
                    color="Region:N",
                )
            )
            st.altair_chart(chart, use_container_width=True)
    except URLError as e:
        st.error(
            """
            **This demo requires internet access.**

            Connection error: %s
        """
            % e.reason
        )


page_names_to_funcs = {
    "—": intro,
    "Plotting Demo": plotting_demo,
    "DataFrame Demo": data_frame_demo,
}

demo_name = st.sidebar.selectbox("Choose a demo", page_names_to_funcs.keys())
await page_names_to_funcs[demo_name]()
```
The data file `agri.csv.gz` can be obtained from the [Stlite repository][5].
## Run the application
Open the HTML file with your browser. Press ++f12++ to monitor the network
traffic. If everything is all right, you will see  all the requests of CSS,
JavaScript and Python wheels go to Mahoraga.

[1]: https://github.com/whitphx/stlite
[2]: https://streamlit.io/
[3]: ../tutorial.md
[4]: https://pyodide.org/en/stable/usage/index.html
[5]: https://raw.githubusercontent.com/whitphx/stlite/main/packages/sharing-editor/public/samples/012_hello/agri.csv.gz
