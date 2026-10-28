// Ace of Angels: Classic Enhanced. Original project shader, MIT licensed.
// Color-only effect: no depth buffer, game hooks, or external shader packages.
uniform float Vibrance < ui_type = "slider"; ui_min = 0.0; ui_max = 0.4;
    ui_label = "Color vibrance"; > = 0.14;
uniform float Contrast < ui_type = "slider"; ui_min = 0.0; ui_max = 0.3;
    ui_label = "Gentle contrast"; > = 0.08;
uniform float Sharpen < ui_type = "slider"; ui_min = 0.0; ui_max = 0.4;
    ui_label = "Detail sharpening"; > = 0.12;
uniform float Bloom < ui_type = "slider"; ui_min = 0.0; ui_max = 0.2;
    ui_label = "Highlight glow"; > = 0.06;
uniform float BloomThreshold < ui_type = "slider"; ui_min = 0.5; ui_max = 0.95;
    ui_label = "Glow threshold"; > = 0.78;
uniform bool SplitPreview < ui_label = "Compare: original left / enhanced right"; > = false;

texture BackBuffer : COLOR;
sampler Scene { Texture = BackBuffer; AddressU = CLAMP; AddressV = CLAMP; };
texture GlowA { Width = BUFFER_WIDTH / 4; Height = BUFFER_HEIGHT / 4; Format = RGBA16F; };
texture GlowB { Width = BUFFER_WIDTH / 4; Height = BUFFER_HEIGHT / 4; Format = RGBA16F; };
sampler GlowASampler { Texture = GlowA; AddressU = CLAMP; AddressV = CLAMP; };
sampler GlowBSampler { Texture = GlowB; AddressU = CLAMP; AddressV = CLAMP; };

void FullscreenVS(uint id : SV_VertexID, out float4 position : SV_Position, out float2 uv : TEXCOORD)
{
    uv = float2((id << 1) & 2, id & 2);
    position = float4(uv * float2(2.0, -2.0) + float2(-1.0, 1.0), 0.0, 1.0);
}

float3 Highlights(float2 uv)
{
    float3 c = tex2D(Scene, uv).rgb;
    // Maximum channel catches saturated engine/weapon light, not only white.
    float peak = max(c.r, max(c.g, c.b));
    return c * smoothstep(BloomThreshold, 1.0, peak);
}

float4 ExtractPS(float4 position : SV_Position, float2 uv : TEXCOORD) : SV_Target
{
    float2 p = float2(BUFFER_RCP_WIDTH, BUFFER_RCP_HEIGHT);
    return float4((Highlights(uv + p) + Highlights(uv - p)
        + Highlights(uv + p * float2(1, -1))
        + Highlights(uv + p * float2(-1, 1))) * 0.25, 1.0);
}

float4 BlurPS(float4 position : SV_Position, float2 uv : TEXCOORD) : SV_Target
{
    float2 stepUV = float2(4.0 * BUFFER_RCP_WIDTH, 0.0);
    float3 c = tex2D(GlowASampler, uv).rgb * 0.227027;
    c += (tex2D(GlowASampler, uv + stepUV * 1.384615).rgb
        + tex2D(GlowASampler, uv - stepUV * 1.384615).rgb) * 0.316216;
    c += (tex2D(GlowASampler, uv + stepUV * 3.230769).rgb
        + tex2D(GlowASampler, uv - stepUV * 3.230769).rgb) * 0.070270;
    return float4(c, 1.0);
}

float4 FinishPS(float4 position : SV_Position, float2 uv : TEXCOORD) : SV_Target
{
    float4 original = tex2D(Scene, uv);
    if (SplitPreview && uv.x < 0.5) return original;
    float2 p = float2(BUFFER_RCP_WIDTH, BUFFER_RCP_HEIGHT);
    float3 average = (tex2D(Scene, uv + float2(p.x, 0)).rgb
        + tex2D(Scene, uv - float2(p.x, 0)).rgb
        + tex2D(Scene, uv + float2(0, p.y)).rgb
        + tex2D(Scene, uv - float2(0, p.y)).rgb) * 0.25;
    // Bound sharpening to reduce halos on tiny HUD letters and stars.
    float3 c = saturate(original.rgb + clamp((original.rgb - average) * Sharpen, -0.015, 0.015));
    // Smooth S curve preserves exact black/white and gently separates midtones.
    c = lerp(c, c * c * (3.0 - 2.0 * c), Contrast);
    float luma = dot(c, float3(0.2126, 0.7152, 0.0722));
    float saturation = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
    c = saturate(lerp(luma.xxx, c, 1.0 + Vibrance * (1.0 - saturation)));
    float2 stepUV = float2(0.0, 4.0 * BUFFER_RCP_HEIGHT);
    float3 glow = tex2D(GlowBSampler, uv).rgb * 0.227027;
    glow += (tex2D(GlowBSampler, uv + stepUV * 1.384615).rgb
        + tex2D(GlowBSampler, uv - stepUV * 1.384615).rgb) * 0.316216;
    glow += (tex2D(GlowBSampler, uv + stepUV * 3.230769).rgb
        + tex2D(GlowBSampler, uv - stepUV * 3.230769).rgb) * 0.070270;
    c = 1.0 - (1.0 - c) * (1.0 - saturate(glow * Bloom));
    return float4(c, original.a);
}

technique ClassicEnhanced < ui_label = "AOA Classic Enhanced";
    ui_tooltip = "Subtle color, contrast, detail and glow. Scroll Lock toggles all effects."; >
{
    pass Extract { VertexShader = FullscreenVS; PixelShader = ExtractPS; RenderTarget = GlowA; }
    pass Blur { VertexShader = FullscreenVS; PixelShader = BlurPS; RenderTarget = GlowB; }
    pass Finish { VertexShader = FullscreenVS; PixelShader = FinishPS; }
}
