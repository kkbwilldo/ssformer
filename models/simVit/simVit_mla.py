import torch
import torch.nn as nn
import torch.nn.functional as F
from functools import partial
import warnings
from timm.models.layers import DropPath, to_2tuple, trunc_normal_
from timm.models.registry import register_model
from timm.models.vision_transformer import _cfg
import math


class Mlp(nn.Module):
    def __init__(self, in_features, hidden_features=None, out_features=None, act_layer=nn.GELU, drop=0., linear=False):
        super().__init__()
        out_features = out_features or in_features
        hidden_features = hidden_features or in_features
        self.fc1 = nn.Linear(in_features, hidden_features)
        self.dwconv = DWConv(hidden_features)
        self.act = act_layer()
        self.fc2 = nn.Linear(hidden_features, out_features)
        self.drop = nn.Dropout(drop)
        self.linear = linear
        if self.linear:
            self.relu = nn.ReLU(inplace=True)
        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def forward(self, x, H, W):
        x = self.fc1(x)
        if self.linear:
            x = self.relu(x)
        x = self.dwconv(x, H, W)
        x = self.act(x)
        x = self.drop(x)
        x = self.fc2(x)
        x = self.drop(x)
        return x

# class CenterAttention_max_pool(nn.Module):
#     """
#     """
#     # self.attn = CenterAttention(
#     #     dim=dim,
#     #     num_heads=num_heads, qkv_bias=qkv_bias, qk_scale=qk_scale,
#     #     attn_drop=attn_drop, proj_drop=drop)
#     def __init__(self,
#                  dim,
#                  num_heads=1,
#                  qkv_bias=True,
#                  qk_scale=None,
#                  attn_drop=0.,
#                  proj_drop=0.,
#                  stride=1,
#                  padding=True,
#                  kernel_size=3):
#         super().__init__()
#         assert dim % num_heads == 0, f"dim {dim} should be divided by num_heads {num_heads}."
#         self.k_size = kernel_size  # kernel size
#         self.stride = stride  # stride
#         # self.pat_size = patch_size  # patch size
#
#         self.in_channels = dim  # origin channel is 3, patch channel is in_channel
#         self.num_heads = num_heads
#         self.head_channel = dim // num_heads
#         # self.dim = dim # patch embedding dim
#         # it seems that padding must be true to make unfolded dim matchs query dim h*w*ks*ks
#         self.pad_size = kernel_size // 2 if padding is True else 0  # padding size
#         self.pad = nn.ZeroPad2d(self.pad_size)  # padding around the input
#         self.scale = qk_scale or (dim // num_heads)**-0.5
#         self.unfold = nn.Unfold(kernel_size=self.k_size, stride=self.stride, padding=0, dilation=1)
#         self.maxpool = nn.MaxPool2d(kernel_size=3, stride=1, padding=1)
#         # self.avgpool = nn.AvgPool2d(kernel_size=3, stride=1, padding=1)
#         self.qkv_bias = qkv_bias
#         self.q_proj = nn.Linear(dim, dim, bias=qkv_bias)
#         self.kv_proj = nn.Linear(dim, dim * 2, bias=qkv_bias)
#         self.attn_drop = nn.Dropout(attn_drop)
#         self.softmax = nn.Softmax(dim=-1)
#         self.proj = nn.Linear(dim, dim)
#         self.proj_drop = nn.Dropout(proj_drop)
#
#     def _init_weights(self, m):
#         if isinstance(m, nn.Linear):
#             trunc_normal_(m.weight, std=.02)
#             if isinstance(m, nn.Linear) and m.bias is not None:
#                 nn.init.constant_(m.bias, 0)
#         elif isinstance(m, nn.LayerNorm):
#             nn.init.constant_(m.bias, 0)
#             nn.init.constant_(m.weight, 1.0)
#         elif isinstance(m, nn.Conv2d):
#             fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
#             fan_out //= m.groups
#             m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
#             if m.bias is not None:
#                 m.bias.data.zero_()
#
#     def forward(self, x, H, W):
#         B, N, C = x.shape
#         x = x.reshape(B, H, W, C)
#         assert C == self.in_channels
#
#         self.pat_size_h = (H+2 * self.pad_size-self.k_size) // self.stride+1
#         self.pat_size_w = (W+2 * self.pad_size-self.k_size) // self.stride+1
#         self.num_patch = self.pat_size_h * self.pat_size_w
#
#
#         q = self.q_proj(x)  # (B, H, W, C)
#         q = q.permute(0, 3, 1, 2)  # (B, C, H, W)
#         q = self.maxpool(q).permute(0, 2, 3, 1) # (B, H, W, C)
#         # q = self.avgpool(q).permute(0, 2, 3, 1)  # (B, H, W, C)
#         q = q.reshape(B, H, W, self.num_heads, self.head_channel).permute(0, 3, 1, 2, 4)  # (B, NumHeads, H, W, HeadC)
#
#         # q = self.pad(q).permute(0, 1, 3, 4, 2)  # (B, NumH, H, W, HeadC)
#         # query need to be copied by (self.k_size*self.k_size) times
#         q = q.unsqueeze(dim=4)
#         q = q * self.scale
#
#         # if stride is not 1, q should be masked to match ks*ks*patch
#         # ...
#
#         # (2, B, NumHeads, HeadsC, H, W)
#         kv = self.kv_proj(x).reshape(B, H, W, 2, self.num_heads, self.head_channel).permute(3, 0, 4, 5, 1, 2)
#
#         kv = self.pad(kv)  # (2, B, NumH, HeadC, H, W)
#         kv = kv.permute(0, 1, 2, 4, 5, 3)
#         H, W = H + self.pad_size * 2, W + self.pad_size * 2
#
#         # unfold plays role of conv2d to get patch data
#         kv = kv.permute(0, 1, 2, 5, 3, 4).reshape(2 * B, -1, H, W)
#         kv = self.unfold(kv)
#         kv = kv.reshape(2, B, self.num_heads, self.head_channel, self.k_size**2,
#                         self.num_patch)  # (2, B, NumH, HC, ks*ks, NumPatch)
#         kv = kv.permute(0, 1, 2, 5, 4, 3)  # (2, B, NumH, NumPatch, ks*ks, HC)
#         k, v = kv[0], kv[1]
#
#         # (B, NumH, NumPatch, 1, HeadC)
#         q = q.reshape(B, self.num_heads, self.num_patch, 1, self.head_channel)
#         attn = (q @ k.transpose(-2, -1))  # (B, NumH, NumPatch, ks*ks, ks*ks)
#         attn = self.softmax(attn)  # softmax last dim
#         attn = self.attn_drop(attn)
#
#         out = (attn @ v).squeeze(3)  # (B, NumH, NumPatch, HeadC)
#         out = out.permute(0, 2, 1, 3).reshape(B, self.pat_size_h, self.pat_size_w, C)  # (B, Ph, Pw, C)
#         out = self.proj(out)
#         out = self.proj_drop(out)
#         out = out.reshape(B, -1, C)
#         return out
#
#     def flops(self):
#         flops = 0
#         # q_proj and kv_proj
#         flops += (2 * self.in_channels - 0 if self.qkv_bias is True else 1) * self.in_channels * 3
#         # q* self.scale
#         H, W = self.input_resolution
#         flops += H * W * self.in_channels
#         # q@k
#         flops += self.num_heads * self.num_patch * (2 * self.head_channel - 1) * self.k_size**2
#         # attn @ v
#         flops += self.num_heads * self.num_patch * self.k_size**2 * (2 * self.k_size**2 - 1) * self.head_channel
#         # proj out
#         flops += self.pat_size_h * self.pat_size_w * (2 * self.in_channels - 1) * self.in_channels
#
#         return flops


class CenterAttention(nn.Module):
    """
    """
    # self.attn = CenterAttention(
    #     dim=dim,
    #     num_heads=num_heads, qkv_bias=qkv_bias, qk_scale=qk_scale,
    #     attn_drop=attn_drop, proj_drop=drop)
    def __init__(self,
                 dim,
                 num_heads=1,
                 qkv_bias=True,
                 qk_scale=None,
                 attn_drop=0.,
                 proj_drop=0.,
                 stride=1,
                 padding=True,
                 kernel_size=3):
        super().__init__()
        assert dim % num_heads == 0, f"dim {dim} should be divided by num_heads {num_heads}."
        self.k_size = kernel_size  # kernel size
        self.stride = stride  # stride
        # self.pat_size = patch_size  # patch size

        self.in_channels = dim  # origin channel is 3, patch channel is in_channel
        self.num_heads = num_heads
        self.head_channel = dim // num_heads
        # self.dim = dim # patch embedding dim
        # it seems that padding must be true to make unfolded dim matchs query dim h*w*ks*ks
        self.pad_size = kernel_size // 2 if padding is True else 0  # padding size
        self.pad = nn.ZeroPad2d(self.pad_size)  # padding around the input
        self.scale = qk_scale or (dim // num_heads)**-0.5
        self.unfold = nn.Unfold(kernel_size=self.k_size, stride=self.stride, padding=0, dilation=1)

        self.qkv_bias = qkv_bias
        self.q_proj = nn.Linear(dim, dim, bias=qkv_bias)
        self.kv_proj = nn.Linear(dim, dim * 2, bias=qkv_bias)
        self.attn_drop = nn.Dropout(attn_drop)
        self.softmax = nn.Softmax(dim=-1)
        self.proj = nn.Linear(dim, dim)
        self.proj_drop = nn.Dropout(proj_drop)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def forward(self, x, H, W):
        B, N, C = x.shape
        x = x.reshape(B, H, W, C)
        assert C == self.in_channels

        self.pat_size_h = (H+2 * self.pad_size-self.k_size) // self.stride+1
        self.pat_size_w = (W+2 * self.pad_size-self.k_size) // self.stride+1
        self.num_patch = self.pat_size_h * self.pat_size_w

        # (B, NumHeads, H, W, HeadC)
        q = self.q_proj(x).reshape(B, H, W, self.num_heads, self.head_channel).permute(0, 3, 1, 2, 4)
        # q = self.pad(q).permute(0, 1, 3, 4, 2)  # (B, NumH, H, W, HeadC)
        # query need to be copied by (self.k_size*self.k_size) times
        q = q.unsqueeze(dim=4)
        q = q * self.scale
        # if stride is not 1, q should be masked to match ks*ks*patch
        # ...

        # (2, B, NumHeads, HeadsC, H, W)
        kv = self.kv_proj(x).reshape(B, H, W, 2, self.num_heads, self.head_channel).permute(3, 0, 4, 5, 1, 2)

        kv = self.pad(kv)  # (2, B, NumH, HeadC, H, W)
        kv = kv.permute(0, 1, 2, 4, 5, 3)
        H, W = H + self.pad_size * 2, W + self.pad_size * 2

        # unfold plays role of conv2d to get patch data
        kv = kv.permute(0, 1, 2, 5, 3, 4).reshape(2 * B, -1, H, W)
        kv = self.unfold(kv)
        kv = kv.reshape(2, B, self.num_heads, self.head_channel, self.k_size**2,
                        self.num_patch)  # (2, B, NumH, HC, ks*ks, NumPatch)
        kv = kv.permute(0, 1, 2, 5, 4, 3)  # (2, B, NumH, NumPatch, ks*ks, HC)
        k, v = kv[0], kv[1]

        # (B, NumH, NumPatch, 1, HeadC)
        q = q.reshape(B, self.num_heads, self.num_patch, 1, self.head_channel)
        attn = (q @ k.transpose(-2, -1))  # (B, NumH, NumPatch, ks*ks, ks*ks)
        attn = self.softmax(attn)  # softmax last dim
        attn = self.attn_drop(attn)

        out = (attn @ v).squeeze(3)  # (B, NumH, NumPatch, HeadC)
        out = out.permute(0, 2, 1, 3).reshape(B, self.pat_size_h, self.pat_size_w, C)  # (B, Ph, Pw, C)
        out = self.proj(out)
        out = self.proj_drop(out)
        out = out.reshape(B, -1, C)
        return out

class Attention(nn.Module):
    def __init__(self, dim, num_heads=8, qkv_bias=False, qk_scale=None, attn_drop=0., proj_drop=0., sr_ratio=1, linear=False):
        super().__init__()
        assert dim % num_heads == 0, f"dim {dim} should be divided by num_heads {num_heads}."

        self.dim = dim
        self.num_heads = num_heads
        head_dim = dim // num_heads
        self.scale = qk_scale or head_dim ** -0.5

        self.q = nn.Linear(dim, dim, bias=qkv_bias)
        self.kv = nn.Linear(dim, dim * 2, bias=qkv_bias)
        self.attn_drop = nn.Dropout(attn_drop)
        self.proj = nn.Linear(dim, dim)
        self.proj_drop = nn.Dropout(proj_drop)

        self.linear = linear
        self.sr_ratio = sr_ratio

        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def forward(self, x, H, W):
        B, N, C = x.shape
        q = self.q(x).reshape(B, N, self.num_heads, C // self.num_heads).permute(0, 2, 1, 3)
        kv = self.kv(x).reshape(B, -1, 2, self.num_heads, C // self.num_heads).permute(2, 0, 3, 1, 4)
        k, v = kv[0], kv[1]
        attn = (q @ k.transpose(-2, -1)) * self.scale
        attn = attn.softmax(dim=-1)
        attn = self.attn_drop(attn)
        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        x = self.proj(x)
        x = self.proj_drop(x)
        return x


class Block(nn.Module):

    def __init__(self, dim, num_heads, mlp_ratio=4., qkv_bias=False, qk_scale=None, drop=0., attn_drop=0.,
                 drop_path=0., act_layer=nn.GELU, norm_layer=nn.LayerNorm, linear=False, last_stage=False):
        super().__init__()
        self.norm1 = norm_layer(dim)
        if not last_stage:
            self.attn = CenterAttention(
                dim=dim,
                num_heads=num_heads, qkv_bias=qkv_bias, qk_scale=qk_scale,
                attn_drop=attn_drop, proj_drop=drop)
            # self.attn = CenterAttention_max_pool(
            #     dim=dim,
            #     num_heads=num_heads, qkv_bias=qkv_bias, qk_scale=qk_scale,
            #     attn_drop=attn_drop, proj_drop=drop)
        else:
            self.attn = Attention(
                dim,
                num_heads=num_heads, qkv_bias=qkv_bias, qk_scale=qk_scale,
                attn_drop=attn_drop, proj_drop=drop, linear=linear)
        self.drop_path = DropPath(drop_path) if drop_path > 0. else nn.Identity()
        self.norm2 = norm_layer(dim)
        mlp_hidden_dim = int(dim * mlp_ratio)
        self.mlp = Mlp(in_features=dim, hidden_features=mlp_hidden_dim, act_layer=act_layer, drop=drop, linear=linear)

        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def forward(self, x, H, W):
        x = x + self.drop_path(self.attn(self.norm1(x), H, W))
        x = x + self.drop_path(self.mlp(self.norm2(x), H, W))

        return x


class PatchEmbed(nn.Module):
    """ Image to Patch Embedding
    """

    def __init__(self, img_size=224, patch_size=16, in_chans=3, embed_dim=768):
        super().__init__()
        img_size = to_2tuple(img_size)
        patch_size = to_2tuple(patch_size)

        self.img_size = img_size
        self.patch_size = patch_size
        # assert img_size[0] % patch_size[0] == 0 and img_size[1] % patch_size[1] == 0, \
        #     f"img_size {img_size} should be divided by patch_size {patch_size}."
        self.H, self.W = img_size[0] // patch_size[0], img_size[1] // patch_size[1]
        self.num_patches = self.H * self.W
        self.proj = nn.Conv2d(in_chans, embed_dim, kernel_size=patch_size, stride=patch_size)
        self.norm = nn.LayerNorm(embed_dim)
        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def forward(self, x):
        B, C, H, W = x.shape

        x = self.proj(x).flatten(2).transpose(1, 2)
        x = self.norm(x)
        H, W = H // self.patch_size[0], W // self.patch_size[1]

        return x, H, W


class simvit(nn.Module):
    def __init__(self, img_size=224, in_chans=3, num_classes=1000, embed_dims=[64, 128, 256, 512],
                 num_heads=[1, 2, 4, 8], mlp_ratios=[4, 4, 4, 4], qkv_bias=False, qk_scale=None, drop_rate=0.,
                 attn_drop_rate=0., drop_path_rate=0., norm_layer=nn.LayerNorm,
                 depths=[3, 4, 6, 3], num_stages=4, linear=False):
        super().__init__()
        self.num_classes = num_classes
        self.depths = depths
        self.num_stages = num_stages

        dpr = [x.item() for x in torch.linspace(0, drop_path_rate, sum(depths))]  # stochastic depth decay rule
        cur = 0

        for i in range(num_stages):
            patch_embed = PatchEmbed(img_size=img_size if i == 0 else img_size // (2 ** (i+1)),
                                            patch_size=4 if i == 0 else 2,
                                            in_chans=in_chans if i == 0 else embed_dims[i-1],
                                            embed_dim=embed_dims[i])
            block = nn.ModuleList([Block(
                dim=embed_dims[i], num_heads=num_heads[i], mlp_ratio=mlp_ratios[i], qkv_bias=qkv_bias, qk_scale=qk_scale,
                drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[cur + j], norm_layer=norm_layer,
                linear=linear, last_stage=(i==num_stages-1))
                for j in range(depths[i])])

            norm = norm_layer(embed_dims[i])
            cur += depths[i]

            setattr(self, f"patch_embed{i + 1}", patch_embed)
            setattr(self, f"block{i + 1}", block)
            setattr(self, f"norm{i + 1}", norm)

        # classification head
        self.head = nn.Linear(embed_dims[3], num_classes) if num_classes > 0 else nn.Identity()

        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def freeze_patch_emb(self):
        self.patch_embed1.requires_grad = False

    @torch.jit.ignore
    def no_weight_decay(self):
        return {'pos_embed1', 'pos_embed2', 'pos_embed3', 'pos_embed4', 'cls_token'}

    def get_classifier(self):
        return self.head

    def reset_classifier(self, num_classes, global_pool=''):
        self.num_classes = num_classes
        self.head = nn.Linear(self.embed_dim, num_classes) if num_classes > 0 else nn.Identity()

    def forward_features(self, x):
        B = x.shape[0]
        outs = []
        for i in range(self.num_stages):
            patch_embed = getattr(self, f"patch_embed{i + 1}")
            block = getattr(self, f"block{i + 1}")
            norm = getattr(self, f"norm{i + 1}")
            x, H, W = patch_embed(x)
            for blk in block:
                x = blk(x, H, W)
            x = norm(x)
            outs.append(x.reshape(B, H, W, -1).permute(0, 3, 1, 2))
            if i != self.num_stages - 1:
                x = x.reshape(B, H, W, -1).permute(0, 3, 1, 2).contiguous()

        return outs

    def forward(self, x):
        x = self.forward_features(x)
#        print(x[0].shape)
#        x = self.head(x)

        return x


class DWConv(nn.Module):
    def __init__(self, dim=768):
        super(DWConv, self).__init__()
        self.dwconv = nn.Conv2d(dim, dim, 3, 1, 1, bias=True, groups=dim)

    def forward(self, x, H, W):
        B, N, C = x.shape
        x = x.transpose(1, 2).view(B, C, H, W)
        x = self.dwconv(x)
        x = x.flatten(2).transpose(1, 2)

        return x


def _conv_filter(state_dict, patch_size=16):
    """ convert patch embedding weight from manual patchify + linear proj to conv"""
    out_dict = {}
    for k, v in state_dict.items():
        if 'patch_embed.proj.weight' in k:
            v = v.reshape((v.shape[0], 3, patch_size, patch_size))
        out_dict[k] = v

    return out_dict



@register_model
def simvit_micro(pretrained=False, **kwargs):        # source:3.4M 0.6G  ours:3.33M 0.65G  192.168.20.6
    model = simvit(
        embed_dims=[32, 64, 160, 256], num_heads=[1, 2, 5, 8], mlp_ratios=[8, 8, 4, 4], qkv_bias=True,
        norm_layer=partial(nn.LayerNorm, eps=1e-6), depths=[2, 3, 3, 2], **kwargs)
    model.default_cfg = _cfg()

    return model

@register_model
def simvit_tiny(pretrained=False, **kwargs):          # source:13.1M 2.1G ours:12.99M 2.51G  192.168.20.7
    model = simvit(
        embed_dims=[64, 128, 320, 512], num_heads=[1, 2, 5, 8], mlp_ratios=[8, 8, 4, 4], qkv_bias=True,
        norm_layer=partial(nn.LayerNorm, eps=1e-6), depths=[2, 4, 3, 2], **kwargs)
    model.default_cfg = _cfg()

    return model


@register_model
def simvit_small(pretrained=False, **kwargs):
    model = simvit(
        embed_dims=[64, 128, 320, 512], num_heads=[1, 2, 5, 8], mlp_ratios=[8, 8, 4, 4], qkv_bias=True,
        norm_layer=partial(nn.LayerNorm, eps=1e-6), depths=[3, 6, 13, 3], **kwargs)
    model.default_cfg = _cfg()

    return model


@register_model
def simvit_medium(pretrained=False, **kwargs):         # 51.3 M 10.9G
    model = simvit(
        embed_dims=[64, 128, 320, 512], num_heads=[1, 2, 5, 8], mlp_ratios=[8, 8, 4, 4], qkv_bias=True,
        norm_layer=partial(nn.LayerNorm, eps=1e-6), depths=[3, 8, 30, 3], **kwargs)
    model.default_cfg = _cfg()
    return model

@register_model
def simvit_large(pretrained=False, **kwargs):           # 62.51M 12.15 G
    model = simvit(
        embed_dims=[64, 128, 320, 512], num_heads=[1, 2, 5, 8], mlp_ratios=[4, 4, 4, 4], qkv_bias=True,
        norm_layer=partial(nn.LayerNorm, eps=1e-6), depths=[3, 8, 40, 3], **kwargs)
    model.default_cfg = _cfg()

    return model

@register_model
def simvit_huge(pretrained=False, **kwargs):             # 90.73M 18.17 G
    model = simvit(
        embed_dims=[64, 128, 320, 512], num_heads=[1, 2, 5, 8], mlp_ratios=[4, 4, 4, 4], qkv_bias=True,
        norm_layer=partial(nn.LayerNorm, eps=1e-6), depths=[3, 12, 62, 3], **kwargs)
    model.default_cfg = _cfg()

    return model



from einops import rearrange
from torch.nn import *
from mmcv.cnn import build_activation_layer, build_norm_layer
from timm.models.layers import DropPath
from einops.layers.torch import Rearrange
import numpy as np
import torch
from torch.nn import Module, ModuleList, Upsample
from mmcv.cnn import ConvModule
from torch.nn import Sequential, Conv2d, UpsamplingBilinear2d
import torch.nn as nn


def resize(input,
           size=None,
           scale_factor=None,
           mode='nearest',
           align_corners=None,
           warning=True):
    if warning:
        if size is not None and align_corners:
            input_h, input_w = tuple(int(x) for x in input.shape[2:])
            output_h, output_w = tuple(int(x) for x in size)
            if output_h > input_h or output_w > output_h:
                if ((output_h > 1 and output_w > 1 and input_h > 1
                     and input_w > 1) and (output_h - 1) % (input_h - 1)
                        and (output_w - 1) % (input_w - 1)):
                    warnings.warn(
                        f'When align_corners={align_corners}, '
                        'the output would more aligned if '
                        f'input size {(input_h, input_w)} is `x+1` and '
                        f'out size {(output_h, output_w)} is `nx+1`')
    return F.interpolate(input, size, scale_factor, mode, align_corners)


class MLP(nn.Module):
    """
    Linear Embedding
    """

    def __init__(self, input_dim=512, embed_dim=768):
        super().__init__()
        self.proj = nn.Linear(input_dim, embed_dim)

    def forward(self, x):
        x = x.flatten(2).transpose(1, 2)
        x = self.proj(x)
        return x


from mmcv.cnn import build_norm_layer
class conv(nn.Module):
    """
    Linear Embedding
    """

    def __init__(self, input_dim=512, embed_dim=768):
        super().__init__()
        
        self.proj = nn.Sequential(nn.Conv2d(input_dim, embed_dim, 3, padding=1, bias=False), build_norm_layer(dict(type='BN', requires_grad=True), embed_dim)[1],nn.ReLU(),
            nn.Conv2d(embed_dim, embed_dim, 3, padding=1, bias=False), build_norm_layer(dict(type='BN', requires_grad=True), embed_dim)[1],nn.ReLU())

    def forward(self, x):
        x = self.proj(x)
        x = x.flatten(2).transpose(1, 2)
        return x

class Decoder(nn.Module):
    """
    SegFormer: Simple and Efficient Design for Semantic Segmentation with Transformers
    """

    def __init__(self, dims, dim, class_num=2):
        super(Decoder, self).__init__()
        self.num_classes = class_num

        c1_in_channels, c2_in_channels, c3_in_channels, c4_in_channels = dims[0], dims[1], dims[2], dims[3]
        embedding_dim = dim

        self.linear_c4 = conv(input_dim=c4_in_channels, embed_dim=embedding_dim)
        self.linear_c3 = conv(input_dim=c3_in_channels, embed_dim=embedding_dim)
        self.linear_c2 = conv(input_dim=c2_in_channels, embed_dim=embedding_dim)
        self.linear_c1 = conv(input_dim=c1_in_channels, embed_dim=embedding_dim)

        self.linear_fuse = ConvModule(in_channels=embedding_dim * 4, out_channels=embedding_dim, kernel_size=1,norm_cfg=dict(type='BN', requires_grad=True))
        self.linear_fuse34 = ConvModule(in_channels=embedding_dim * 2, out_channels=embedding_dim, kernel_size=1,norm_cfg=dict(type='BN', requires_grad=True))
        self.linear_fuse2 = ConvModule(in_channels=embedding_dim * 2, out_channels=embedding_dim, kernel_size=1,norm_cfg=dict(type='BN', requires_grad=True))
        self.linear_fuse1 = ConvModule(in_channels=embedding_dim * 2, out_channels=embedding_dim, kernel_size=1,norm_cfg=dict(type='BN', requires_grad=True))

        self.linear_pred = nn.Conv2d(embedding_dim, self.num_classes, kernel_size=1)
        self.dropout = nn.Dropout(0.1)

    def forward(self, inputs):

        c1, c2, c3, c4 = inputs
        ############## MLP decoder on C1-C4 ###########
        n, _, h, w = c4.shape

        _c4 = self.linear_c4(c4).permute(0, 2, 1).reshape(n, -1, c4.shape[2], c4.shape[3])
        _c4 = resize(_c4, size=c1.size()[2:], mode='bilinear', align_corners=False)
        _c3 = self.linear_c3(c3).permute(0, 2, 1).reshape(n, -1, c3.shape[2], c3.shape[3])
        _c3 = resize(_c3, size=c1.size()[2:], mode='bilinear', align_corners=False)
        _c2 = self.linear_c2(c2).permute(0, 2, 1).reshape(n, -1, c2.shape[2], c2.shape[3])
        _c2 = resize(_c2, size=c1.size()[2:], mode='bilinear', align_corners=False)
        _c1 = self.linear_c1(c1).permute(0, 2, 1).reshape(n, -1, c1.shape[2], c1.shape[3])
        
        _c = self.linear_fuse(torch.cat([_c4, _c3, _c2, _c1], dim=1))
        x = self.dropout(_c)
        x = self.linear_pred(x)
        return x


class simVit_mla(nn.Module):
    def __init__(self, class_num=2, **kwargs):
        super(simVit_mla, self).__init__()
        self.class_num = class_num
        ######################################load_weight
        self.backbone = simvit_tiny()
        #####################################
        self.decode_head = Decoder(dims=[64, 128, 320, 512], dim=256, class_num=class_num)
        self._init_weights() # load pretrain
        
    def forward(self, x):
        features = self.backbone(x)
        features = self.decode_head(features)
        up = UpsamplingBilinear2d(scale_factor=4)
        features = up(features)
        return features

    def _init_weights(self):
        pretrained_dict = torch.load('/mnt/DATA-1/DATA-2/Feilong/scformer/models/simVit/simvit_small_checkpoint_224.pth')
        model_dict = self.backbone.state_dict()
        pretrained_dict = {k: v for k, v in pretrained_dict.items() if k in model_dict}
        model_dict.update(pretrained_dict)
        self.backbone.load_state_dict(model_dict)  
        print("successfully loaded!!!!")   


from torchinfo import summary
sct_b2 = simVit_mla(class_num = 1)
summary(sct_b2, (1, 3, 512, 512))
from thop import profile
import torch
input = torch.randn(1, 3, 352, 352).to('cuda')
macs, params = profile(sct_b2, inputs=(input, ))
print('macs:',macs/1000000000)
print('params:',params/1000000)


