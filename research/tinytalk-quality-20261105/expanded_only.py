"""Train only newly added MLP units while keeping inherited parameters exact."""


class ExpandedOnly:
    def __init__(self, model):
        import torch
        self.model=model
        cfg=model.config.tinytalk_mlp_expansion
        self.old=cfg['old_width'];self.new=cfg['new_width']
        assert self.old==1024 and self.new==1280
        model.requires_grad_(False)
        self.partial=[];self.active_elements=0;self.hooks=[]
        def original(module):
            return module.parametrizations.weight.original if hasattr(module,'parametrizations') else module.weight
        def enable(parameter,axis,label,cutoff=None):
            cutoff=self.old if cutoff is None else cutoff
            parameter.requires_grad_(True)
            index=[slice(None)]*parameter.ndim;index[axis]=slice(0,cutoff);index=tuple(index)
            fixed=parameter[index].detach().clone()
            mask=torch.ones_like(parameter);mask[index]=0
            self.hooks.append(parameter.register_hook(lambda gradient,mask=mask:gradient*mask))
            self.partial.append((parameter,index,fixed,label))
            self.active_elements+=parameter.numel()-fixed.numel()
        for i,block in enumerate(model.transformer.h):
            enable(original(block.mlp.c_fc),0,f'layer{i}.mlp.input')
            enable(block.mlp.c_fc.bias,0,f'layer{i}.mlp.input_bias')
            enable(original(block.mlp.c_proj),1,f'layer{i}.mlp.output')
        self.type_elements=0
        if getattr(model.config,'tinytalk_answer_type_token_ids',None):
            base=model.config.tinytalk_answer_type_base_vocab_size
            assert all(base<=i<model.config.vocab_size for i in model.config.tinytalk_answer_type_token_ids.values())
            self.type_elements=(model.config.vocab_size-base)*model.config.hidden_size
            enable(original(model.transformer.wte),0,'added_answer_type_embeddings',cutoff=base)
        self.control_elements=0
        if hasattr(model.transformer.wte,'control_flat'):
            control=model.transformer.wte.control_flat;control.requires_grad_(True)
            self.control_elements=control.numel();self.active_elements+=self.control_elements
        self.whole=[(p,p.detach().clone(),name) for name,p in model.named_parameters() if not p.requires_grad]
        self.parameter_ids={id(p) for p in model.parameters()}
        self.frozen_elements=sum(p.numel() for p,_,_ in self.whole)+sum(v.numel() for _,_,v,_ in self.partial)
        assert self.active_elements==1050624+self.type_elements+self.control_elements
        assert self.frozen_elements+self.active_elements==sum(p.numel() for p in model.parameters())
        model.config.tinytalk_expanded_mlp_only=True
        model.config.tinytalk_word_embeddings_frozen_in_sft=True

    def restore(self):
        """Also protect fixed slices from optimizer decay and floating zero updates."""
        import torch
        with torch.no_grad():
            for parameter,index,saved,_ in self.partial:
                parameter[index].copy_(saved)

    def verify(self):
        import torch
        assert {id(p) for p in self.model.parameters()}==self.parameter_ids
        for parameter,saved,name in self.whole:
            assert torch.equal(parameter.detach(),saved),f'Frozen parameter changed: {name}'
        for parameter,index,saved,name in self.partial:
            assert torch.equal(parameter.detach()[index],saved),f'Frozen slice changed: {name}'

    def summary(self):
        return {'effective_trainable_elements':self.active_elements,'inherited_elements_frozen':self.frozen_elements,
            'new_answer_type_embedding_elements':self.type_elements,
            'independent_control_input_elements':self.control_elements,
            'optimizer_parameter_elements':sum(p.numel() for p in self.model.parameters() if p.requires_grad),
            'old_width':self.old,'new_width':self.new,
            'policy':'Gradient masks, exact restoration of inherited slices after each update, and checkpoint guards'}
