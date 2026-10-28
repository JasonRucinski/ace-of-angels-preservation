// Diagnostic only; never installed by classic_enhanced.py.
// Encodes the high 24 bits of sampled depth into RGB for byte-exact PNG inspection.
// Use point sampling: interpolation of this wrapper's NaN float representation
// destroys the packed depth. Source: locally authored, MIT licensed.
texture Depth : DEPTH;
sampler DepthSampler { Texture = Depth; MinFilter = POINT; MagFilter = POINT; MipFilter = POINT; };
void VS(uint id : SV_VertexID, out float4 pos : SV_Position, out float2 uv : TEXCOORD)
{
    uv = float2((id << 1) & 2, id & 2);
    pos = float4(uv * float2(2, -2) + float2(-1, 1), 0, 1);
}
float4 PS(float4 pos : SV_Position, float2 uv : TEXCOORD) : SV_Target
{
    uint bits = asuint(tex2D(DepthSampler, uv).r);
    return float4((bits >> 24) & 255, (bits >> 16) & 255, (bits >> 8) & 255, 255) / 255.0;
}
technique DepthProbe { pass { VertexShader = VS; PixelShader = PS; } }
