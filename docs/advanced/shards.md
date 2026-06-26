# Generate sharded conda repodata locally
[CEP 16][1] introduced sharded repodata to supersede the old non-standard
[JLAP][2] protocol. Channels like conda-forge and [prefix.dev][3] have already
gained support for the CEP, and Mahoraga plays well with them.

*[JLAP]: JSON lines append penultimate

!!! info "Note"

    Add a prefix.dev channel to the section `[upstream.conda.channel-alias]` in
    your `mahoraga.toml` to enable support for that channel. No configuration
    is required for conda-forge.

However, when working with dependencies from another conda channel, you will
still find yourself waiting for package managers to download the full
`repodata.json.zst` (or even worse, `repodata.json.bz2` or `repodata.json`) from
time to time. If you have multiple clients within the local network, Mahoraga
can help by reducing the network traffic. It downloads the full repodata every
hour in the background (HTTP 304 caching occurs when there is no change) and
then convert them to static sharded repodata which can be directly served by
Nginx or Caddy.

To enable this feature, add the channels and platforms you need to the `[shard]`
section. Remember that you don't need this for conda-forge or prefix.dev:

```toml title="mahoraga.toml"
[shard]
my-awesome-channel = [
    "linux-64",
    "linux-aarch64",
    "noarch",
    "osx-64",
    "osx-arm64",
    "win-64",
]
```

Restart Mahoraga and it will start preparing the sharded repodata for you. The
status can be tracked in `log/mahoraga.log`.

[1]: https://conda.org/learn/ceps/cep-0016/
[2]: https://github.com/dholth/ceps/blob/c95ef8f80dcabcc0cb1ac5974595bbc70620ec32/cep-jlap.md
[3]: https://prefix.dev/channels
