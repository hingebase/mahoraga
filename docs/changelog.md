# Release Notes
{%- for title, section in changelog %}
## {{ title }}
{%- for group, commits in section | dictsort %}
### {{ group[1:] }}
{%- for commit in commits | reverse %}
- {{ commit }}
{%- endfor %}
{%- endfor %}
{%- endfor %}
First beta release.
