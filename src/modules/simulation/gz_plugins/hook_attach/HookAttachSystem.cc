#include <atomic>
#include <chrono>
#include <limits>
#include <mutex>
#include <string>

#include <gz/common/Console.hh>
#include <gz/plugin/Register.hh>

#include <gz/msgs/boolean.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>

#include <gz/sim/System.hh>
#include <gz/sim/EntityComponentManager.hh>

#include <gz/sim/components/Name.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Link.hh>
#include <gz/sim/components/ParentEntity.hh>
#include <gz/sim/components/DetachableJoint.hh>

// MagnetForceSystem icin (asagida, ayni ceviri biriminde -- nedeni orada yazili)
#include <cmath>
#include <vector>
#include <gz/msgs/vector3d.pb.h>
#include <gz/math/Pose3.hh>
#include <gz/math/Vector3.hh>
#include <gz/sim/Link.hh>
#include <gz/sim/Util.hh>

namespace hook_attach
{

// Same runtime-joint mechanism as gz-sim's own DetachableJoint system (an
// entity carrying only a components::DetachableJoint is materialized into a
// real fixed joint by the physics system -- confirmed against the gz-sim8
// DetachableJoint.cc source). The one deliberate behavioral difference: the
// stock system's `attachRequested` flag defaults to true and is never reset
// by Configure() or by detaching, so it auto-attaches the instant its
// configured child model becomes resolvable -- fine for a child that is
// spawned already touching its parent, wrong for a payload that is dropped
// long before the drone is meant to pick it up. Here attach only ever
// becomes true in response to an explicit attach message (sent by
// payload.py only after hook_sensor_service.py reports a genuine contact),
// and the target child model name comes from that message instead of being
// fixed in SDF, since the dropped payload's spawned name isn't known until
// PayloadDropSystem actually drops it.
class HookAttachSystem :
  public gz::sim::System,
  public gz::sim::ISystemConfigure,
  public gz::sim::ISystemPreUpdate
{
public:
  void Configure(const gz::sim::Entity &_entity,
                 const std::shared_ptr<const sdf::Element> &_sdf,
                 gz::sim::EntityComponentManager &,
                 gz::sim::EventManager &) override
  {
    ownModelEntity_ = _entity;

    if (_sdf && _sdf->HasElement("parent_link"))
      parentLinkName_ = _sdf->Get<std::string>("parent_link");
    if (_sdf && _sdf->HasElement("child_link"))
      childLinkName_ = _sdf->Get<std::string>("child_link");
    if (_sdf && _sdf->HasElement("attach_topic"))
      attachTopic_ = _sdf->Get<std::string>("attach_topic");
    if (_sdf && _sdf->HasElement("detach_topic"))
      detachTopic_ = _sdf->Get<std::string>("detach_topic");
    if (_sdf && _sdf->HasElement("output_topic"))
      outputTopic_ = _sdf->Get<std::string>("output_topic");

    const bool subAttachOk = node_.Subscribe(attachTopic_, &HookAttachSystem::OnAttachRequest, this);
    const bool subDetachOk = node_.Subscribe(detachTopic_, &HookAttachSystem::OnDetachRequest, this);
    statePub_ = node_.Advertise<gz::msgs::Boolean>(outputTopic_);

    gzwarn << "[HookAttach] LOADED"
           << " subAttachOk=" << (subAttachOk ? "true" : "false")
           << " subDetachOk=" << (subDetachOk ? "true" : "false")
           << " parent_link=" << parentLinkName_
           << " child_link=" << childLinkName_
           << " attach_topic=" << attachTopic_
           << " detach_topic=" << detachTopic_
           << " output_topic=" << outputTopic_
           << "\n";
  }

  void PreUpdate(const gz::sim::UpdateInfo &,
                 gz::sim::EntityComponentManager &_ecm) override
  {
    if (parentLinkEntity_ == gz::sim::kNullEntity)
      parentLinkEntity_ = FindLinkInModel(_ecm, ownModelEntity_, parentLinkName_);

    if (detachRequested_)
    {
      detachRequested_ = false;
      if (isAttached_)
      {
        _ecm.RequestRemoveEntity(jointEntity_);
        jointEntity_ = gz::sim::kNullEntity;
        childModelEntity_ = gz::sim::kNullEntity;
        childLinkEntity_ = gz::sim::kNullEntity;
        isAttached_ = false;
        PublishState(false);
        gzwarn << "[HookAttach] DETACHED\n";
      }
      else
      {
        gzwarn << "[HookAttach] Detach requested but nothing is attached; ignoring\n";
      }
    }

    if (!attachRequested_ || isAttached_)
      return;

    if (parentLinkEntity_ == gz::sim::kNullEntity)
      return; // retry next tick

    std::string childName;
    {
      std::lock_guard<std::mutex> lock(pendingMutex_);
      childName = pendingChildModelName_;
    }

    if (childModelEntity_ == gz::sim::kNullEntity)
      childModelEntity_ = FindModel(_ecm, childName);
    if (childModelEntity_ != gz::sim::kNullEntity && childLinkEntity_ == gz::sim::kNullEntity)
      childLinkEntity_ = FindLinkInModel(_ecm, childModelEntity_, childLinkName_);

    if (childModelEntity_ == gz::sim::kNullEntity || childLinkEntity_ == gz::sim::kNullEntity)
      return; // child not spawned/resolvable yet -- keep retrying, same as stock DetachableJoint

    jointEntity_ = _ecm.CreateEntity();
    _ecm.CreateComponent(jointEntity_,
        gz::sim::components::DetachableJoint({parentLinkEntity_, childLinkEntity_, "fixed"}));
    isAttached_ = true;
    attachRequested_ = false;
    PublishState(true);
    gzwarn << "[HookAttach] ATTACHED child_model=" << childName
           << " joint_entity=" << jointEntity_ << "\n";
  }

private:
  void OnAttachRequest(const gz::msgs::StringMsg &_msg)
  {
    if (isAttached_)
    {
      gzwarn << "[HookAttach] Already attached; ignoring attach request for " << _msg.data() << "\n";
      return;
    }
    {
      std::lock_guard<std::mutex> lock(pendingMutex_);
      pendingChildModelName_ = _msg.data();
    }
    attachRequested_ = true;
    gzwarn << "[HookAttach] Attach requested for child_model=" << _msg.data() << "\n";
  }

  void OnDetachRequest(const gz::msgs::Boolean &_msg)
  {
    if (_msg.data())
      detachRequested_ = true;
  }

  void PublishState(bool _attached)
  {
    gz::msgs::Boolean msg;
    msg.set_data(_attached);
    statePub_.Publish(msg);
  }

  gz::sim::Entity FindModel(gz::sim::EntityComponentManager &_ecm, const std::string &name)
  {
    gz::sim::Entity out = gz::sim::kNullEntity;
    _ecm.Each<gz::sim::components::Name, gz::sim::components::Model>(
      [&](const gz::sim::Entity &e,
          const gz::sim::components::Name *n,
          const gz::sim::components::Model *) -> bool
      {
        if (n && n->Data() == name) { out = e; return false; }
        return true;
      });
    return out;
  }

  gz::sim::Entity FindLinkInModel(gz::sim::EntityComponentManager &_ecm,
                                   gz::sim::Entity modelEnt,
                                   const std::string &linkName)
  {
    gz::sim::Entity out = gz::sim::kNullEntity;
    _ecm.Each<gz::sim::components::Name,
              gz::sim::components::Link,
              gz::sim::components::ParentEntity>(
      [&](const gz::sim::Entity &e,
          const gz::sim::components::Name *n,
          const gz::sim::components::Link *,
          const gz::sim::components::ParentEntity *p) -> bool
      {
        if (!n || !p) return true;
        if (p->Data() != modelEnt) return true;

        const std::string &nn = n->Data();
        const bool exact = (nn == linkName);
        const bool suff =
          (nn.size() >= (linkName.size() + 2)) &&
          (nn.rfind("::" + linkName) == (nn.size() - (2 + linkName.size())));

        if (exact || suff) { out = e; return false; }
        return true;
      });
    return out;
  }

private:
  gz::transport::Node node_;
  gz::transport::Node::Publisher statePub_;

  std::string parentLinkName_{"hook_rope_link"};
  std::string childLinkName_{"link"};
  std::string attachTopic_{"/hook/attach"};
  std::string detachTopic_{"/hook/detach"};
  std::string outputTopic_{"/hook/state"};

  gz::sim::Entity ownModelEntity_{gz::sim::kNullEntity};
  gz::sim::Entity parentLinkEntity_{gz::sim::kNullEntity};
  gz::sim::Entity childModelEntity_{gz::sim::kNullEntity};
  gz::sim::Entity childLinkEntity_{gz::sim::kNullEntity};
  gz::sim::Entity jointEntity_{gz::sim::kNullEntity};

  std::mutex pendingMutex_;
  std::string pendingChildModelName_;

  std::atomic<bool> attachRequested_{false};
  std::atomic<bool> detachRequested_{false};
  bool isAttached_{false};
};


// ===========================================================================
//  MagnetForceSystem -- GERCEK MANYETIK CEKIM  (GOREV K / D, 2026-09-05)
// ===========================================================================
//
// NEDEN VAR. Bu yapida "manyetik cekim" simule EDILMIYORDU. Arac SDF'inin
// kendi notu da bunu yaziyordu ("SADECE GORSEL: manyetik cekim simule
// EDILMIYOR"). Gorev katmani bosluga bir taklit koymustu: miknatis menzile
// girince ARACIN tutma hedefi kancayi agiza getirecek yone kaydiriliyordu.
//
// O TAKLIT OLCULDU VE CALISMIYOR. 2026-09-05 kosumu, yedi ardisik adim:
//     [MIKNATIS] adim 1: d=33.8 mm -> hedef (+58.946, -7.657)
//     [MIKNATIS] adim 2: d=33.8 mm -> hedef (+58.931, -7.670)
//     ...
//     [MIKNATIS] adim 7: d=33.4 mm
// Yedi adimda mesafe 33.8 -> 33.4 mm. Sebep yapisal: kanca guvertede
// DURUYOR; araci kaydirmak kancayi surukemiyor, yalnizca ipi egiyor.
// Daha onceki bir A/B'de (P3) ayni taklit kontrol koluna karsi hicbir
// kazanc uretmemisti (yanal medyan 59.9 -> 60.3 mm).
//
// COZUM (operator, 2026-09-05): "iki miknatisin birbirini cekmesi gibi"
// calissin ve KANCAYI ceksin. Yani araca degil, hook_body_link'e GERCEK
// KUVVET uygulanir; tepkisi de Newton'un ucuncu yasasi geregi yuke.
//
// NEDEN AYRI BIR DOSYA/HEDEF DEGIL: yeni bir CMake alt dizini eklemek
// CMake'i yeniden yapilandirir ve PX4'un yapilandirma adimi submodule
// kontrolu (yani AG ERISIMI) tetikleyebilir. Ayni ceviri biriminde ikinci
// bir sistem kaydetmek, `ninja HookAttachSystem` ile tek dosya derlemesi
// demektir -- yeniden yapilandirma yok, ag yok. Ikisi zaten ayni fiziksel
// olayin (kanca <-> yuk kenetlenmesi) iki asamasi. Derleme ortami serbestce
// yeniden yapilandirilabildiginde ayri bir hedefe bolunmelidir.
//
// KUVVET YASASI -- her terim turetildi:
//
//   F(d) = F_max * (d0 / (d0 + d))^2        d <= range, yoksa 0
//
//   * F_max = 0.40 N. ALT SINIR: kanca guverteye dayaninca onu KAYDIRABILMELI.
//     Kanca kutlesi 0.020 kg (arac SDF'i), agirligi 0.196 N; SDF'de <surface>
//     tanimli olmadigi icin mu varsayilani 1.0, yani statik surtunme ~0.196 N.
//     0.40 N bunun ~2 kati -- taklidin basaramadigi is tam olarak buydu.
//     UST SINIR: cozucu kararliligi ve asagidaki sonumleme.
//   * d0 = 0.025 m. Menzil kenarinda (d = 0.05) kuvvet
//     0.40 * (0.025/0.075)^2 = 0.044 N eder. Bu, serbest asili kancayi
//     35 mm yanal ofsetten geri getiren sarkac kuvvetinin
//     (m*g*x/L = 0.196 * 0.035 / 0.53 = 0.013 N) ~3.4 kati, yani menzil
//     kenarinda bile ise yarar.
//   * damping c = 2.0 N*s/m, BAGIL hiza uygulanir. Esdeger yay katsayisi
//     k = F_max/range = 8 N/m ve m = 0.020 kg icin kritik sonumleme
//     c_crit = 2*sqrt(k*m) = 0.80 N*s/m; 2.0 bunun 2.5 kati, yani ASIRI
//     SONUMLU -- asim ve salinim yok. Azami kuvvette yaklasma hizi
//     v = F/c = 0.20 m/s'de doyar; yuvaya girdiginde temas onu durdurur ve
//     oturma kapisinin 0.05 m/s'lik hiz esigi saglanabilir hale gelir.
//
// NE SIMULE EDILMIYOR: gercek dipol alani (uzak alanda ~1/d^4). Yukaridaki
// yasa MENZIL ICINDE tekduze artan, sinirli ve sonumlu bir yaklasimdir;
// amaci gercek B alanini yeniden uretmek degil, "miknatis kancayi yuvaya
// oturtur" davranisini fizik cozucusunun icinde gerceklestirmektir. Buyukluk
// yukaridaki iki fiziksel esikten (surtunme, sarkac) turetildi.
class MagnetForceSystem :
  public gz::sim::System,
  public gz::sim::ISystemConfigure,
  public gz::sim::ISystemPreUpdate
{
public:
  void Configure(const gz::sim::Entity &_entity,
                 const std::shared_ptr<const sdf::Element> &_sdf,
                 gz::sim::EntityComponentManager &,
                 gz::sim::EventManager &) override
  {
    ownModelEntity_ = _entity;

    if (_sdf)
    {
      if (_sdf->HasElement("hook_link"))        hookLinkName_    = _sdf->Get<std::string>("hook_link");
      if (_sdf->HasElement("payload_prefix"))   payloadPrefix_   = _sdf->Get<std::string>("payload_prefix");
      if (_sdf->HasElement("payload_link"))     payloadLinkName_ = _sdf->Get<std::string>("payload_link");
      if (_sdf->HasElement("hook_magnet_z"))    hookMagnetZ_     = _sdf->Get<double>("hook_magnet_z");
      if (_sdf->HasElement("payload_magnet_z")) payloadMagnetZ_  = _sdf->Get<double>("payload_magnet_z");
      if (_sdf->HasElement("range"))            range_           = _sdf->Get<double>("range");
      if (_sdf->HasElement("max_force"))        maxForce_        = _sdf->Get<double>("max_force");
      if (_sdf->HasElement("falloff"))          falloff_         = _sdf->Get<double>("falloff");
      if (_sdf->HasElement("damping"))          damping_         = _sdf->Get<double>("damping");
      if (_sdf->HasElement("state_topic"))      stateTopic_      = _sdf->Get<std::string>("state_topic");
    }

    statePub_ = node_.Advertise<gz::msgs::Vector3d>(stateTopic_);

    gzwarn << "[Magnet] LOADED"
           << " hook_link=" << hookLinkName_
           << " payload_prefix=" << payloadPrefix_
           << " range=" << range_
           << " max_force=" << maxForce_
           << " falloff=" << falloff_
           << " damping=" << damping_
           << " state_topic=" << stateTopic_
           << "\n";
  }

  void PreUpdate(const gz::sim::UpdateInfo &_info,
                 gz::sim::EntityComponentManager &_ecm) override
  {
    if (_info.paused)
      return;

    if (hookLinkEntity_ == gz::sim::kNullEntity)
    {
      hookLinkEntity_ = FindLinkInModel(_ecm, ownModelEntity_, hookLinkName_);
      if (hookLinkEntity_ == gz::sim::kNullEntity)
        return;                                  // model henuz cozulmedi
      // Hiz bileseni istege bagli olarak olusturulur; sonumleme terimi ona
      // bakiyor, bu yuzden bir kez acikca isteniyor.
      gz::sim::Link(hookLinkEntity_).EnableVelocityChecks(_ecm, true);
    }

    // Yukler ucus sirasinda DUSURULEREK olusuyor, yani entity'ler sonradan
    // beliriyor. Her tikte tum modelleri taramak yerine periyodik tazeleme.
    const auto now = _info.simTime;
    if (payloads_.empty() || (now - lastScan_) > std::chrono::seconds(1))
    {
      lastScan_ = now;
      RescanPayloads(_ecm);
    }
    if (payloads_.empty())
      return;

    const gz::math::Pose3d hookPose = gz::sim::worldPose(hookLinkEntity_, _ecm);
    const gz::math::Vector3d hookMagnet =
      hookPose.Pos() + hookPose.Rot().RotateVector({0.0, 0.0, hookMagnetZ_});

    // EN YAKIN yuk. Birden fazla yuk sahnede duruyor (biri birakilmis, biri
    // hala aracin altinda olabilir); miknatis fizik olarak en yakinini ceker.
    gz::sim::Entity bestLink = gz::sim::kNullEntity;
    gz::math::Vector3d bestDelta;
    double bestDist = std::numeric_limits<double>::max();

    for (const auto &pl : payloads_)
    {
      const gz::math::Pose3d pPose = gz::sim::worldPose(pl, _ecm);
      const gz::math::Vector3d pMagnet =
        pPose.Pos() + pPose.Rot().RotateVector({0.0, 0.0, payloadMagnetZ_});
      const gz::math::Vector3d delta = pMagnet - hookMagnet;
      const double d = delta.Length();
      if (d < bestDist) { bestDist = d; bestDelta = delta; bestLink = pl; }
    }

    const bool active = (bestLink != gz::sim::kNullEntity) && (bestDist <= range_);
    double fMag = 0.0;

    if (active && bestDist > 1e-9)
    {
      const double k = falloff_ / (falloff_ + bestDist);
      fMag = maxForce_ * k * k;

      gz::math::Vector3d force = bestDelta.Normalized() * fMag;

      // SONUMLEME: bagil hiza karsi. Kancayi yuvaya SOKAN sey cekim,
      // icinde SABITLEYEN sey budur -- sonumsuz bir miknatis kancayi
      // iceri firlatip disari sektirir.
      gz::sim::Link hookLink(hookLinkEntity_);
      gz::sim::Link payLink(bestLink);
      const auto vHook = hookLink.WorldLinearVelocity(_ecm);
      const auto vPay  = payLink.WorldLinearVelocity(_ecm);
      if (vHook.has_value())
      {
        const gz::math::Vector3d vRel =
          vHook.value() - (vPay.has_value() ? vPay.value() : gz::math::Vector3d::Zero);
        force -= vRel * damping_;
      }

      // KANCAYA ceker...
      hookLink.AddWorldForce(_ecm, force);
      // ...ve YUKE esit-zit tepki (Newton 3). Yuk 0.15 kg ve zeminde
      // duruyor, statik surtunmesi ~1.47 N, yani 0.4 N onu kaydirmaz --
      // ama atlamak, olmayan bir kuvvet uydurmak olurdu.
      payLink.AddWorldForce(_ecm, -force);
    }

    // DURUM YAYINI ~10 Hz (salt olcum; gorev tarafi bunu logluyor).
    if ((now - lastPub_) > std::chrono::milliseconds(100))
    {
      lastPub_ = now;
      gz::msgs::Vector3d m;
      m.set_x((bestLink == gz::sim::kNullEntity) ? -1.0 : bestDist);
      m.set_y(fMag);
      m.set_z(active ? 1.0 : 0.0);
      statePub_.Publish(m);
    }
  }

private:
  void RescanPayloads(gz::sim::EntityComponentManager &_ecm)
  {
    payloads_.clear();
    std::vector<gz::sim::Entity> models;
    _ecm.Each<gz::sim::components::Name, gz::sim::components::Model>(
      [&](const gz::sim::Entity &e,
          const gz::sim::components::Name *n,
          const gz::sim::components::Model *) -> bool
      {
        if (n && n->Data().rfind(payloadPrefix_, 0) == 0)
          models.push_back(e);
        return true;
      });

    for (const auto &m : models)
    {
      const gz::sim::Entity l = FindLinkInModel(_ecm, m, payloadLinkName_);
      if (l != gz::sim::kNullEntity)
      {
        gz::sim::Link(l).EnableVelocityChecks(_ecm, true);
        payloads_.push_back(l);
      }
    }
  }

  // HookAttachSystem'inkiyle ayni arama; ayni ceviri biriminde oldugu icin
  // kopyalanmadi, bagimsiz bir kopya olarak duruyor (o sinifin uyesi).
  gz::sim::Entity FindLinkInModel(gz::sim::EntityComponentManager &_ecm,
                                  gz::sim::Entity modelEnt,
                                  const std::string &linkName)
  {
    gz::sim::Entity out = gz::sim::kNullEntity;
    _ecm.Each<gz::sim::components::Name,
              gz::sim::components::Link,
              gz::sim::components::ParentEntity>(
      [&](const gz::sim::Entity &e,
          const gz::sim::components::Name *n,
          const gz::sim::components::Link *,
          const gz::sim::components::ParentEntity *p) -> bool
      {
        if (!n || !p) return true;
        if (p->Data() != modelEnt) return true;
        const std::string &nn = n->Data();
        const bool exact = (nn == linkName);
        const bool suff =
          (nn.size() >= (linkName.size() + 2)) &&
          (nn.rfind("::" + linkName) == (nn.size() - (2 + linkName.size())));
        if (exact || suff) { out = e; return false; }
        return true;
      });
    return out;
  }

  gz::transport::Node node_;
  gz::transport::Node::Publisher statePub_;

  std::string hookLinkName_{"hook_body_link"};
  std::string payloadPrefix_{"payload_"};
  std::string payloadLinkName_{"link"};
  std::string stateTopic_{"/hook/magnet/state"};

  // Kanca miknatis yuzu, hook_body_link cercevesinde: arac SDF'i
  // hook_magnet_visual <pose>0 0 -0.06565</pose>.
  double hookMagnetZ_{-0.06565};
  // Yuk miknatis oturagi, payload link cercevesinde: hook_seating.py
  // geometri tablosu, CAD z 0.00 -> link z +0.008.
  double payloadMagnetZ_{0.008};

  double range_{0.05};        // operator: 3-5 cm
  double maxForce_{0.40};     // N   -- turetme yukarida
  double falloff_{0.025};     // m
  double damping_{2.0};       // N*s/m

  gz::sim::Entity ownModelEntity_{gz::sim::kNullEntity};
  gz::sim::Entity hookLinkEntity_{gz::sim::kNullEntity};
  std::vector<gz::sim::Entity> payloads_;
  std::chrono::steady_clock::duration lastScan_{std::chrono::seconds(0)};
  std::chrono::steady_clock::duration lastPub_{std::chrono::seconds(0)};
};

} // namespace hook_attach

GZ_ADD_PLUGIN(hook_attach::HookAttachSystem,
              gz::sim::System,
              gz::sim::ISystemConfigure,
              gz::sim::ISystemPreUpdate)

GZ_ADD_PLUGIN(hook_attach::MagnetForceSystem,
              gz::sim::System,
              gz::sim::ISystemConfigure,
              gz::sim::ISystemPreUpdate)
