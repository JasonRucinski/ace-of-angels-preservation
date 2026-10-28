// Ace of Angels: Classic Enhanced. Original project shader, MIT licensed.
// Standard depth protects the sky; the optional UI add-on runs this before HUD drawing.
uniform bool ProtectSky < ui_label = "Preserve original sky colors"; > = true;
uniform bool DepthAvailable < source = "bufready_depth"; >;
// Set by classic_ui_addon, never stored as a user preference.
uniform bool PreUIActive < source = "aoa_pre_ui"; > = false;
uniform float Vibrance < ui_type = "slider"; ui_min = 0.0; ui_max = 1.5;
    ui_label = "Color vibrance"; > = 0.95;
uniform float Contrast < ui_type = "slider"; ui_min = 0.0; ui_max = 0.6;
    ui_label = "Contrast"; > = 0.30;
uniform float ShadowLift < ui_type = "slider"; ui_min = 0.0; ui_max = 1.0;
    ui_label = "Shadow detail"; > = 0.75;
uniform float Exposure < ui_type = "slider"; ui_min = -1.0; ui_max = 1.0;
    ui_label = "Exposure (stops)"; > = 0.35;
uniform float ColorGrade < ui_type = "slider"; ui_min = 0.0; ui_max = 1.0;
    ui_label = "Teal / warm color grade"; > = 0.65;
uniform float Vignette < ui_type = "slider"; ui_min = 0.0; ui_max = 0.5;
    ui_label = "Edge vignette"; > = 0.18;
uniform float Sharpen < ui_type = "slider"; ui_min = 0.0; ui_max = 0.4;
    ui_label = "Detail sharpening"; > = 0.22;
uniform float Bloom < ui_type = "slider"; ui_min = 0.0; ui_max = 1.2;
    ui_label = "Highlight glow"; > = 0.65;
uniform float BloomThreshold < ui_type = "slider"; ui_min = 0.2; ui_max = 0.95;
    ui_label = "Glow threshold"; > = 0.40;
uniform float BloomRadius < ui_type = "slider"; ui_min = 1.0; ui_max = 4.0;
    ui_label = "Glow spread"; > = 2.5;
uniform float LightGlow < ui_type = "slider"; ui_min = 0.0; ui_max = 4.0;
    ui_label = "Radiant lights"; > = 2.2;
uniform float LightColor < ui_type = "slider"; ui_min = 0.0; ui_max = 1.5;
    ui_label = "Light halo color"; > = 0.8;
uniform float LightStreaks < ui_type = "slider"; ui_min = 0.0; ui_max = 4.0;
    ui_label = "Cinematic light streaks"; > = 2.2;
uniform float StreakLength < ui_type = "slider"; ui_min = 16.0; ui_max = 120.0;
    ui_label = "Streak reach (pixels at 1920 wide)"; > = 64.0;
uniform float StreakThreshold < ui_type = "slider"; ui_min = 0.5; ui_max = 0.95;
    ui_label = "Streak highlight threshold"; > = 0.72;
uniform bool EngineCaptureOff < source = "aoa_engine_capture"; > = false;
uniform float EngineGlow < ui_type = "slider"; ui_min = 0.0; ui_max = 3.0;
    ui_label = "Engine exhaust"; > = 1.6;
uniform float4 EngineStart0 < source = "aoa_engine"; > = 0.0;
uniform float4 EngineStart1 < source = "aoa_engine"; > = 0.0;
uniform float4 EngineEnd0 < source = "aoa_engine"; > = 0.0;
uniform float4 EngineEnd1 < source = "aoa_engine"; > = 0.0;
uniform bool SplitPreview < ui_label = "Compare: original left / enhanced right"; > = false;

texture BackBuffer : COLOR;
sampler Scene { Texture = BackBuffer; AddressU = CLAMP; AddressV = CLAMP; };
texture SceneDepth : DEPTH;
texture WorldDepth : AOA_WORLD_DEPTH;
sampler WorldDepthSampler { Texture = WorldDepth; MinFilter = POINT; MagFilter = POINT;
    MipFilter = POINT; AddressU = CLAMP; AddressV = CLAMP; };
sampler DepthSampler { Texture = SceneDepth; MinFilter = POINT; MagFilter = POINT;
    MipFilter = POINT; AddressU = CLAMP; AddressV = CLAMP; };
texture GlowA { Width = BUFFER_WIDTH / 4; Height = BUFFER_HEIGHT / 4; Format = RGBA16F; };
texture GlowB { Width = BUFFER_WIDTH / 4; Height = BUFFER_HEIGHT / 4; Format = RGBA16F; };
sampler GlowASampler { Texture = GlowA; AddressU = CLAMP; AddressV = CLAMP; };
sampler GlowBSampler { Texture = GlowB; AddressU = CLAMP; AddressV = CLAMP; };
// Half-resolution light layer retains tiny station windows lost in wide bloom.
texture LightA { Width = BUFFER_WIDTH / 2; Height = BUFFER_HEIGHT / 2; Format = RGBA16F; };
texture LightB { Width = BUFFER_WIDTH / 2; Height = BUFFER_HEIGHT / 2; Format = RGBA16F; };
sampler LightASampler { Texture = LightA; AddressU = CLAMP; AddressV = CLAMP; };
sampler LightBSampler { Texture = LightB; AddressU = CLAMP; AddressV = CLAMP; };
texture StreakA { Width = BUFFER_WIDTH / 4; Height = BUFFER_HEIGHT / 2; Format = RGBA16F; };
texture StreakB { Width = BUFFER_WIDTH / 4; Height = BUFFER_HEIGHT / 2; Format = RGBA16F; };
sampler StreakASampler { Texture = StreakA; AddressU = BORDER; AddressV = BORDER; };
sampler StreakBSampler { Texture = StreakB; AddressU = BORDER; AddressV = BORDER; };

void FullscreenVS(uint id : SV_VertexID, out float4 position : SV_Position, out float2 uv : TEXCOORD)
{
    uv = float2((id << 1) & 2, id & 2);
    position = float4(uv * float2(2.0, -2.0) + float2(-1.0, 1.0), 0.0, 1.0);
}

float Foreground(float2 uv)
{
    if (!ProtectSky) return 1.0;
    // The pre-HUD add-on supplies the actual typed D16 view, before UI depth clears.
    if (PreUIActive) return tex2D(WorldDepthSampler, uv).r < 0.999999 ? 1.0 : 0.0;
    if (!DepthAvailable) return 0.0;
    // This pinned dgVoodoo D3D11 path exposes packed depth through a float SRV.
    // Numeric float comparisons see NaNs in the far scene. Compare the bits.
    // Live probe: sky's high 24 bits = 0xffffe0; geometry is below that range.
    uint packedDepth = asuint(tex2D(DepthSampler, uv).r);
    return packedDepth < 0xffffe000 ? 1.0 : 0.0;
}

float3 Highlights(float2 uv)
{
    float3 c = tex2D(Scene, uv).rgb;
    // Maximum channel catches saturated engine/weapon light, not only white.
    float peak = max(c.r, max(c.g, c.b));
    return c * smoothstep(BloomThreshold, 1.0, peak) * Foreground(uv);
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
    float2 stepUV = float2(4.0 * BUFFER_RCP_WIDTH * BloomRadius, 0.0);
    float3 c = tex2D(GlowASampler, uv).rgb * 0.227027;
    c += (tex2D(GlowASampler, uv + stepUV * 1.384615).rgb
        + tex2D(GlowASampler, uv - stepUV * 1.384615).rgb) * 0.316216;
    c += (tex2D(GlowASampler, uv + stepUV * 3.230769).rgb
        + tex2D(GlowASampler, uv - stepUV * 3.230769).rgb) * 0.070270;
    return float4(c, 1.0);
}

float3 BrightLight(float2 uv)
{
    float3 c = tex2D(Scene, uv).rgb;
    float peak = max(c.r, max(c.g, c.b));
    // Only bright source pixels seed the extra glow; shadow lift cannot seed it.
    float3 hue = pow(saturate(c / max(peak, 0.0001)), (1.0 + LightColor).xxx);
    return hue * peak * smoothstep(0.60, 0.95, peak) * Foreground(uv);
}

float4 LightExtractPS(float4 position : SV_Position, float2 uv : TEXCOORD) : SV_Target
{
    float2 p = float2(BUFFER_RCP_WIDTH, BUFFER_RCP_HEIGHT) * 0.5;
    // Peak pooling preserves sub-pixel lights before the soft blur.
    float3 c = max(max(BrightLight(uv + p), BrightLight(uv - p)),
                   max(BrightLight(uv + p * float2(1, -1)),
                       BrightLight(uv + p * float2(-1, 1))));
    return float4(c, 1.0);
}

float4 LightBlurPS(float4 position : SV_Position, float2 uv : TEXCOORD) : SV_Target
{
    float2 p = float2(2.0 * BUFFER_RCP_WIDTH, 0.0);
    float3 c = tex2D(LightASampler, uv).rgb * 0.227027;
    c += (tex2D(LightASampler, uv + p * 1.384615).rgb
        + tex2D(LightASampler, uv - p * 1.384615).rgb) * 0.316216;
    c += (tex2D(LightASampler, uv + p * 3.230769).rgb
        + tex2D(LightASampler, uv - p * 3.230769).rgb) * 0.070270;
    return float4(c, 1.0);
}

float3 StreakSource(float2 uv)
{
    // LightA contains only original foreground highlights, before exposure or glow.
    float3 c = tex2D(LightASampler, uv).rgb;
    float peak = max(c.r, max(c.g, c.b));
    float2 p = float2(6.0 * BUFFER_RCP_WIDTH, 4.0 * BUFFER_RCP_HEIGHT);
    float3 surrounding = (tex2D(LightASampler, uv + float2(p.x, 0)).rgb
        + tex2D(LightASampler, uv - float2(p.x, 0)).rgb
        + tex2D(LightASampler, uv + float2(0, p.y)).rgb
        + tex2D(LightASampler, uv - float2(0, p.y)).rgb) * 0.25;
    // Reject broad bright hull areas; compact lights and sharp glints can seed a streak.
    float localContrast = peak - max(surrounding.r, max(surrounding.g, surrounding.b));
    return c * smoothstep(StreakThreshold, 1.0, peak) * smoothstep(0.08, 0.30, localContrast);
}

float4 StreakExtractPS(float4 position : SV_Position, float2 uv : TEXCOORD) : SV_Target
{
    if (LightStreaks <= 0.0) return 0.0;
    float2 p = float2(BUFFER_RCP_WIDTH, 0.0);
    return float4(max(StreakSource(uv - p), StreakSource(uv + p)), 1.0);
}

float4 StreakBlurPS(float4 position : SV_Position, float2 uv : TEXCOORD) : SV_Target
{
    if (LightStreaks <= 0.0) return 0.0;
    float2 p = float2(StreakLength / (1920.0 * 12.0), 0.0);
    float3 c = 0.0;
    float total = 0.0;
    [unroll] for (int i = -12; i <= 12; ++i)
    {
        float t = abs(float(i)) / 12.0;
        float weight = exp(-3.0 * t) * (1.0 - t);
        c += tex2D(StreakASampler, uv + p * float(i)).rgb * weight;
        total += weight;
    }
    return float4(c / total, 1.0);
}

// Projected engine volumes, depth-tested against the unmodified world depth.
float3 EnginePlume(float2 uv, float4 start, float4 end)
{
    if (!PreUIActive || EngineCaptureOff || EngineGlow <= 0.0 || start.w <= 0.0 || end.w <= 0.0) return 0.0;
    float2 aspect = float2(float(BUFFER_WIDTH) / float(BUFFER_HEIGHT), 1.0);
    float2 axis = (end.xy - start.xy) * aspect;
    float2 offset = (uv - start.xy) * aspect;
    float length2 = max(dot(axis, axis), 0.000001);
    float t = clamp(dot(offset, axis) / length2, 0.0, 1.0);
    float radius = lerp(start.w, end.w * 0.15, t);
    float distance = length(offset - t * axis) / max(radius, 0.0001);
    if (distance > 3.5) return 0.0;
    float depth = lerp(start.z, end.z, t);
    if (tex2D(WorldDepthSampler, uv).r + 0.000015 < depth) return 0.0;
    float tail = pow(1.0 - t, 0.65);
    float core = exp(-distance * distance * 8.0) * tail;
    float flame = exp(-distance * distance * 1.5) * tail;
    float halo = exp(-distance * distance * 0.35) * tail;
    return EngineGlow * (core * float3(0.85, 0.95, 1.0)
        + flame * float3(0.04, 0.42, 1.0) + halo * float3(0.01, 0.08, 0.32));
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
    // Lift existing shadow detail without adding a gray floor to empty space.
    c = saturate(pow(c, (1.0 - 0.45 * ShadowLift).xxx) * exp2(Exposure));
    // Smooth S curve restores separation after the shadow lift.
    c = lerp(c, c * c * (3.0 - 2.0 * c), Contrast);
    float luma = dot(c, float3(0.2126, 0.7152, 0.0722));
    float saturation = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
    c = saturate(lerp(luma.xxx, c, 1.0 + Vibrance * (1.0 - saturation)));
    float3 tint = lerp(float3(0.72, 1.03, 1.22), float3(1.16, 1.04, 0.85),
                      smoothstep(0.12, 0.75, luma));
    c = saturate(c * lerp(1.0.xxx, tint, ColorGrade));
    float foreground = Foreground(uv);
    // Flat neutral-black UI panels have no depth of their own. Preserve their
    // base tone so underlying geometry cannot emboss a silhouette into them.
    float rawPeak = max(original.r, max(original.g, original.b));
    float rawChroma = rawPeak - min(original.r, min(original.g, original.b));
    float neutralShadow = (1.0 - smoothstep(0.002, 0.012, rawChroma))
                        * (1.0 - smoothstep(0.045, 0.075, rawPeak));
    if (ProtectSky) foreground *= 1.0 - neutralShadow;
    float2 edge = uv * 2.0 - 1.0;
    c *= 1.0 - Vignette * smoothstep(0.25, 1.5, dot(edge, edge));
    // Sky skips color/brightness/detail/vignette. Only nearby light spill remains.
    c = lerp(original.rgb, c, foreground);
    float2 stepUV = float2(0.0, 4.0 * BUFFER_RCP_HEIGHT * BloomRadius);
    float3 glow = tex2D(GlowBSampler, uv).rgb * 0.227027;
    glow += (tex2D(GlowBSampler, uv + stepUV * 1.384615).rgb
        + tex2D(GlowBSampler, uv - stepUV * 1.384615).rgb) * 0.316216;
    glow += (tex2D(GlowBSampler, uv + stepUV * 3.230769).rgb
        + tex2D(GlowBSampler, uv - stepUV * 3.230769).rgb) * 0.070270;
    c = 1.0 - (1.0 - c) * (1.0 - saturate(glow * Bloom));
    float2 lightStep = float2(0.0, 2.0 * BUFFER_RCP_HEIGHT);
    float3 light = tex2D(LightBSampler, uv).rgb * 0.227027;
    light += (tex2D(LightBSampler, uv + lightStep * 1.384615).rgb
        + tex2D(LightBSampler, uv - lightStep * 1.384615).rgb) * 0.316216;
    light += (tex2D(LightBSampler, uv + lightStep * 3.230769).rgb
        + tex2D(LightBSampler, uv - lightStep * 3.230769).rgb) * 0.070270;
    // Exponential screen blend rolls off smoothly rather than clipping halos.
    c = 1.0 - (1.0 - c) * exp(-light * LightGlow);
    if (LightStreaks > 0.0)
    {
        float2 streakStep = float2(0.0, BUFFER_RCP_HEIGHT);
        float3 streak = tex2D(StreakBSampler, uv).rgb * 0.5
            + (tex2D(StreakBSampler, uv + streakStep).rgb
            + tex2D(StreakBSampler, uv - streakStep).rgb) * 0.25;
        c = 1.0 - (1.0 - c) * exp(-streak * LightStreaks);
    }
    float3 exhaust = EnginePlume(uv, EngineStart0, EngineEnd0) + EnginePlume(uv, EngineStart1, EngineEnd1);
    c = 1.0 - (1.0 - c) * exp(-exhaust);
    return float4(c, original.a);
}

technique ClassicEnhanced < ui_label = "AOA Classic Enhanced";
    ui_tooltip = "Dramatic color, lifted shadows, cinematic grading and glow. Scroll Lock toggles all effects."; >
{
    pass Extract { VertexShader = FullscreenVS; PixelShader = ExtractPS; RenderTarget = GlowA; }
    pass Blur { VertexShader = FullscreenVS; PixelShader = BlurPS; RenderTarget = GlowB; }
    pass LightExtract { VertexShader = FullscreenVS; PixelShader = LightExtractPS; RenderTarget = LightA; }
    pass LightBlur { VertexShader = FullscreenVS; PixelShader = LightBlurPS; RenderTarget = LightB; }
    pass StreakExtract { VertexShader = FullscreenVS; PixelShader = StreakExtractPS; RenderTarget = StreakA; }
    pass StreakBlur { VertexShader = FullscreenVS; PixelShader = StreakBlurPS; RenderTarget = StreakB; }
    pass Finish { VertexShader = FullscreenVS; PixelShader = FinishPS; }
}
